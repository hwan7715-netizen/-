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
    .report-box {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #e9ecef;
    }
    a {
        color: #1E88E5 !important;
        text-decoration: none;
        font-weight: 500;
    }
    a:hover {
        text-decoration: underline;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 AI 퀀트 주식 분석 대시보드")
st.markdown("---")

# 2. 상태 저장소(Session State) 초기화
if 'saved_reports' not in st.session_state:
    st.session_state.saved_reports = {}
if 'current_view' not in st.session_state:
    st.session_state.current_view = None
if 'force_refresh' not in st.session_state:
    st.session_state.force_refresh = False

api_key = st.text_input("발급받은 Gemini API 키를 입력하세요:", type="password")

# 3. 사이드바: 내 관심 종목 저장소
with st.sidebar:
    st.header("📁 내 관심 종목")
    st.write("분석한 종목은 브라우저를 닫기 전까지 이곳에 임시 저장됩니다.")
    
    if st.session_state.saved_reports:
        for saved_ticker, data in st.session_state.saved_reports.items():
            st.markdown(f"**{saved_ticker}** (최근: {data['time'][11:16]})")
            
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
        st.info("저장된 종목이 없습니다.")

# 4. 메인 검색창 및 실행
ticker_input = st.text_input("분석할 미국 주식 티커 (예: AAPL, TSLA):").upper()

if st.button("새 종목 분석 시작"):
    if ticker_input:
        st.session_state.current_view = ticker_input
        st.session_state.force_refresh = True

target_ticker = st.session_state.current_view
force_refresh = st.session_state.force_refresh

# 5. 분석 및 화면 출력 로직
if target_ticker:
    if target_ticker in st.session_state.saved_reports and not force_refresh:
        st.success(f"📌 저장된 {target_ticker} 데이터를 불러왔습니다. ({st.session_state.saved_reports[target_ticker]['time']})")
        report_data = st.session_state.saved_reports[target_ticker]
        
        # 핵심 지표 출력
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재 주가", f"${report_data['price']:.2f}")
        col2.metric("PER", report_data['pe'])
        col3.metric("20일 이동평균", f"${report_data['ma20']:.2f}")
        col4.metric("RSI (투자심리)", f"{report_data['rsi']:.1f}")
        
        # 차트 2개 나란히 출력 (주가 차트 + RSI 속도계)
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
            news_html = "<ul>"
            for news in report_data['news']:
                news_html += f"<li style='margin-bottom:10px;'><a href='{news['link']}' target='_blank'>{news['title']}</a></li>"
            news_html += "</ul>"
            st.markdown(news_html, unsafe_allow_html=True)
            
        with report_col:
            st.subheader("🤖 AI 퀀트 심층 보고서")
            st.markdown(f"<div class='report-box'>{report_data['ai_report']}</div>", unsafe_allow_html=True)

    else:
        if not api_key:
            st.warning("API 키를 입력해 주세요.")
        else:
            try:
                st.info(f"{target_ticker} 데이터를 수집하고 AI를 호출합니다...")
                time.sleep(0.5)
                stock = yf.Ticker(target_ticker)
                hist = stock.history(period="3mo")
                
                if hist.empty:
                    st.error("데이터를 가져오지 못했습니다. 티커를 확인해 주세요.")
                else:
                    current_price = hist['Close'].iloc[-1]
                    info = stock.info
                    
                    # [버그 수정 1] PER 데이터 유연한 추출
                    pe_raw = info.get('trailingPE', info.get('forwardPE'))
                    pe_ratio = f"{pe_raw:.2f}" if pe_raw else "N/A"
                    
                    # 퀀트 지표
                    ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    delta = hist['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]
                    
                    # [버그 수정 2] 뉴스 수집 및 절대 경로화
                    news_list = stock.news
                    news_data_for_ui = [] 
                    if news_list:
                        for news in news_list[:5]:
                            title = "뉴스 제목 없음"
                            link = news.get('link', '#')
                            if 'title' in news: title = news['title']
                            elif 'content' in news and 'title' in news['content']: 
                                title = news['content']['title']
                                if 'link' in news['content']: link = news['content']['link']
                            
                            if link != '#' and not link.startswith('http'):
                                link = f"https://finance.yahoo.com{link}"
                            news_data_for_ui.append({"title": title, "link": link})
                    raw_headlines_text = "\n".join([f"- {n['title']}" for n in news_data_for_ui])
                    
                    # [기능 부활] 주가 흐름 라인 차트 생성 (Plotly)
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
                    
                    # [가독성 개선] AI 프롬프트 재설계 (엄격한 양식 제한)
                    genai.configure(api_key=api_key)
                    model_name = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods][0]
                    model = genai.GenerativeModel(model_name)
                    
                    prompt = f"""
                    너는 데이터 기반의 월스트리트 수석 퀀트 애널리스트야.
                    [실제 데이터] 종목: {target_ticker} / 현재가: ${current_price:.2f} / 20일 이평선: ${ma20:.2f} / RSI: {current_rsi:.1f}
                    [최근 뉴스]: {raw_headlines_text}

                    위 데이터를 분석하여 아래 양식에 맞춰 '반드시 글머리 기호(-)'를 사용해 간결하고 명확하게 작성해:

                    ### 1. 📈 기술적 분석 및 예측
                    - (이동평균선과 RSI를 기반으로 한 주가 방향성 분석 2줄)
                    
                    ### 2. 🌡️ 펀더멘털 및 시장 감성
                    - (뉴스를 바탕으로 한 호재/악재 판별 및 요약 2줄)

                    ### 3. 💡 최종 투자 전략
                    - **목표 매수가:** $000
                    - **목표 매도가:** $000
                    - **핵심 요약:** (현재 상황에 대한 전문가의 1줄 평)
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
                    
                    # 화면 출력
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("현재 주가", f"${current_price:.2f}")
                    col2.metric("PER", pe_ratio)
                    col3.metric("20일 이동평균", f"${ma20:.2f}")
                    col4.metric("RSI (투자심리)", f"{current_rsi:.1f}")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        st.plotly_chart(line_fig, use_container_width=True)
                    with chart_col2:
                        st.plotly_chart(gauge_fig, use_container_width=True)
                    
                    st.markdown("---")
                    news_col, report_col = st.columns([1, 2])
                    
                    with news_col:
                        st.subheader("📰 최근 주요 뉴스")
                        news_html = "<ul>"
                        for news in news_data_for_ui:
                            # [버그 수정 3] HTML 태그로 외부 링크 강제 열기 (target='_blank')
                            news_html += f"<li style='margin-bottom:10px;'><a href='{news['link']}' target='_blank'>{news['title']}</a></li>"
                        news_html += "</ul>"
                        st.markdown(news_html, unsafe_allow_html=True)
                        
                    with report_col:
                        st.subheader("🤖 AI 퀀트 심층 보고서")
                        # CSS 클래스 적용으로 전문적인 박스 디자인
                        st.markdown(f"<div class='report-box'>{ai_report}</div>", unsafe_allow_html=True)
                        
                    st.success(f"분석 완료! 사이드바에 저장되었습니다.")

            except Exception as e:
                st.error(f"오류 발생: {e}")

st.session_state.force_refresh = False