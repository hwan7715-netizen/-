import streamlit as st
import yfinance as yf
import google.generativeai as genai
import time
from datetime import datetime
import plotly.graph_objects as go

# 1. 화면 설정 및 폰트 강제 통일
st.set_page_config(layout="wide") 
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] {
        font-family: 'Pretendard', sans-serif !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 주식 분석 대시보드")
st.markdown("---")

# 2. 상태 저장소 초기화
if 'saved_reports' not in st.session_state:
    st.session_state.saved_reports = {}
if 'current_view' not in st.session_state:
    st.session_state.current_view = None
if 'force_refresh' not in st.session_state:
    st.session_state.force_refresh = False

api_key = st.text_input("발급받은 Gemini API 키를 입력하세요:", type="password")

# 3. 사이드바: 내 관심 종목 저장소
with st.sidebar:
    st.header("📁 내 관심 종목 보관함")
    st.write("분석한 종목은 브라우저를 닫기 전까지 이곳에 자동 저장됩니다.")
    
    if st.session_state.saved_reports:
        for saved_ticker, data in st.session_state.saved_reports.items():
            st.markdown(f"**{saved_ticker}** (최근 분석: {data['time'][11:16]})")
            
            col_view, col_refresh = st.columns(2)
            with col_view:
                if st.button(f"보기", key=f"view_{saved_ticker}"):
                    st.session_state.current_view = saved_ticker
                    st.session_state.force_refresh = False
            with col_refresh:
                if st.button(f"🔄 갱신", key=f"refresh_{saved_ticker}"):
                    st.session_state.current_view = saved_ticker
                    st.session_state.force_refresh = True
            st.markdown("---")
    else:
        st.info("아직 저장된 종목이 없습니다.")

# 4. 메인 검색창 및 실행
ticker_input = st.text_input("분석할 미국 주식 티커 (예: AAPL, TSLA, NVDA):").upper()

if st.button("새 종목 분석 시작"):
    if ticker_input:
        st.session_state.current_view = ticker_input
        st.session_state.force_refresh = True

target_ticker = st.session_state.current_view
force_refresh = st.session_state.force_refresh

# 5. 분석 및 화면 출력 로직
if target_ticker:
    # 이미 저장된 데이터가 있고 갱신 요청이 아닐 때 (캐시 불러오기)
    if target_ticker in st.session_state.saved_reports and not force_refresh:
        st.success(f"📌 임시 보관함에서 {target_ticker} 데이터를 불러왔습니다. (데이터 기준: {st.session_state.saved_reports[target_ticker]['time']})")
        report_data = st.session_state.saved_reports[target_ticker]
        
        # 핵심 지표 출력
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재 주가", f"${report_data['price']:.2f}")
        col2.metric("PER (주가수익비율)", report_data['pe'])
        col3.metric("20일 이동평균", f"${report_data['ma20']:.2f}")
        col4.metric("RSI (투자심리)", f"{report_data['rsi']:.1f}")
        
        # 차트 2개 나란히 출력
        st.markdown("<br>", unsafe_allow_html=True)
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.plotly_chart(report_data['line_chart'], use_container_width=True)
        with chart_col2:
            st.plotly_chart(report_data['gauge_chart'], use_container_width=True)
        
        # 뉴스 및 AI 보고서 출력
        st.markdown("---")
        news_col, report_col = st.columns([1, 2])
        
        with news_col:
            st.subheader("📰 최근 주요 뉴스")
            for news in report_data['news']:
                st.markdown(f"- [{news['title']}]({news['link']})")
            
        with report_col:
            st.subheader("🤖 AI 보고서")
            with st.container(border=True): # 깔끔한 테두리 박스 적용
                st.write(report_data['ai_report'])

    # 새로 API를 호출하여 분석해야 할 때
    else:
        if not api_key:
            st.warning("API 키를 입력해 주세요.")
        else:
            try:
                st.info(f"{target_ticker} 실시간 데이터를 수집하고 AI 분석을 진행합니다. 잠시만 기다려주세요...")
                time.sleep(0.5)
                stock = yf.Ticker(target_ticker)
                hist = stock.history(period="3mo")
                
                if hist.empty:
                    st.error("데이터를 가져오지 못했습니다. 티커를 정확히 입력했는지 확인해 주세요.")
                else:
                    current_price = hist['Close'].iloc[-1]
                    info = stock.info
                    
                    pe_raw = info.get('trailingPE', info.get('forwardPE'))
                    pe_ratio = f"{pe_raw:.2f}" if pe_raw else "N/A"
                    
                    ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    delta = hist['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]
                    
                    # [버그 수정 1] 절대 실패하지 않는 뉴스 링크 조립 로직
                    news_list = stock.news
                    news_data_for_ui = [] 
                    if news_list:
                        for news in news_list[:5]:
                            title = "뉴스 제목 없음"
                            link = news.get('link', '')
                            
                            if 'title' in news: title = news['title']
                            elif 'content' in news and 'title' in news['content']: 
                                title = news['content']['title']
                                if 'link' in news['content']: link = news['content']['link']
                            
                            # 링크가 비정상적일 경우 완벽한 절대 주소로 강제 변환
                            if not link.startswith('http'):
                                if link.startswith('/'):
                                    link = f"https://finance.yahoo.com{link}"
                                else:
                                    link = f"https://finance.yahoo.com/quote/{target_ticker}/news"
                                    
                            news_data_for_ui.append({"title": title, "link": link})
                            
                    raw_headlines_text = "\n".join([f"- {n['title']}" for n in news_data_for_ui])
                    
                    # 라인 차트 생성
                    line_fig = go.Figure()
                    line_fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name='주가', line=dict(color='#1E88E5', width=2)))
                    line_fig.update_layout(title="📈 최근 3개월 주가 흐름", margin=dict(l=0, r=0, t=40, b=0), font=dict(family="Pretendard"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    
                    # 게이지 차트 생성
                    gauge_fig = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = current_rsi,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "RSI 투자 심리도"},
                        gauge = {
                            'axis': {'range': [0, 100]},
                            'bar': {'color': "#424242"},
                            'steps': [{'range': [0, 30], 'color': "#A5D6A7"}, {'range': [30, 70], 'color': "#EEEEEE"}, {'range': [70, 100], 'color': "#EF9A9A"}],
                        }
                    ))
                    gauge_fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), font=dict(family="Pretendard"))
                    
                    # [버그 수정 2] 내용의 깊이를 살린 심층 프롬프트
                    genai.configure(api_key=api_key)
                    model_name = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods][0]
                    model = genai.GenerativeModel(model_name)
                    
                    prompt = f"""
                    너는 월스트리트 최고의 시니어 퀀트 애널리스트야.
                    [실제 데이터] 종목: {target_ticker} / 현재가: ${current_price:.2f} / 20일 이평선: ${ma20:.2f} / RSI: {current_rsi:.1f}
                    [최근 뉴스]: {raw_headlines_text}

                    위 데이터를 종합하여 초보자도 이해하기 쉽지만, 내용의 깊이가 있는 전문가 수준의 투자 리포트를 작성해.
                    가독성을 위해 반드시 아래의 양식과 [글머리 기호(-)]를 사용하여 구조화된 형태로 작성할 것. (절대 줄글로 대충 쓰지 마)

                    ### 1. 📈 기술적 지표 심층 분석
                    - 20일 이동평균선과 현재가를 비교하여 현재 추세의 강도와 지지/저항선을 상세히 분석해.
                    - RSI 수치를 바탕으로 현재 매수/매도 압력이 어떤지, 단기 변동성이 어떻게 될지 예측해.

                    ### 2. 🌡️ 펀더멘털 및 시장 모멘텀
                    - 제공된 최신 뉴스를 종합하여 현재 시장이 이 기업을 어떻게 평가하고 있는지 분석해.
                    - 단기적인 호재/악재를 명확히 판별하고 향후 예상되는 주가 촉매제(Catalyst)를 적어줘.

                    ### 3. 🎯 월스트리트 AI 최종 투자 전략
                    - **전략 방향:** (적극 매수 / 분할 매수 / 관망 / 분할 매도 / 적극 매도 중 1개 선택)
                    - **목표 매수가:** $000 ~ $000 (구체적인 진입 권장 구간)
                    - **목표 매도가:** $000 ~ $000 (구체적인 청산 권장 구간)
                    - **핵심 요약:** (현재 상황에 대한 전문가의 통찰력 있는 1~2줄 평)
                    """
                    
                    response = model.generate_content(prompt)
                    ai_report = response.text
                    
                    # 데이터 세션 저장
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.saved_reports[target_ticker] = {
                        'time': current_time,
                        'price': current_price,
                        'pe': pe_ratio,
                        'ma20': ma20,
                        'rsi': current_rsi,
                        'news': news_data_for_ui,
                        'line_chart': line_fig,
                        'gauge_chart': gauge_fig,
                        'ai_report': ai_report
                    }
                    
                    # [버그 수정 3] 저장이 끝나면 화면을 즉시 새로고침하여 사이드바에 즉시 반영
                    st.session_state.force_refresh = False
                    st.rerun()

            except Exception as e:
                st.error(f"오류 발생: {e}")