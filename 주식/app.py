import streamlit as st
import yfinance as yf
import google.generativeai as genai
import time
from datetime import datetime
import plotly.graph_objects as go

# 1. 화면 설정 및 전체 폰트 강제 통일 (CSS 주입)
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

# 2. 상태 저장소(Session State) 초기화
if 'saved_reports' not in st.session_state:
    st.session_state.saved_reports = {}
if 'current_view' not in st.session_state:
    st.session_state.current_view = None
if 'force_refresh' not in st.session_state:
    st.session_state.force_refresh = False

api_key = st.text_input("발급받은 Gemini API 키를 입력하세요:", type="password")

# 3. 사이드바: 내 관심 종목 저장소 (버그 수정됨)
with st.sidebar:
    st.header("📁 내 관심 종목")
    st.write("분석한 종목은 브라우저를 닫기 전까지 이곳에 임시 저장합니다.")
    
    if st.session_state.saved_reports:
        for saved_ticker, data in st.session_state.saved_reports.items():
            st.markdown(f"**{saved_ticker}** (최근 분석: {data['time']})")
            
            col_view, col_refresh = st.columns(2)
            with col_view:
                if st.button(f"보관함 보기", key=f"view_{saved_ticker}"):
                    st.session_state.current_view = saved_ticker
                    st.session_state.force_refresh = False
            with col_refresh:
                if st.button(f"🔄 최신화", key=f"refresh_{saved_ticker}"):
                    st.session_state.current_view = saved_ticker
                    st.session_state.force_refresh = True
    else:
        st.info("아직 분석/저장된 종목이 없습니다.")

# 4. 메인 검색창 및 실행 로직
ticker_input = st.text_input("분석할 미국 주식 티커 (예: AAPL, TSLA):").upper()

# [핵심 수정] 새 종목 분석 버튼을 눌렀을 때만 상태를 업데이트하도록 변경
if st.button("새 종목 분석 시작"):
    if ticker_input:
        st.session_state.current_view = ticker_input
        st.session_state.force_refresh = True

target_ticker = st.session_state.current_view
force_refresh = st.session_state.force_refresh

# 5. 분석 화면 출력 로직
if target_ticker:
    # 이미 저장된 데이터 불러오기 (캐싱 활용)
    if target_ticker in st.session_state.saved_reports and not force_refresh:
        st.success(f"저장된 {target_ticker} 분석 데이터를 불러왔습니다. (데이터 기준일: {st.session_state.saved_reports[target_ticker]['time']})")
        report_data = st.session_state.saved_reports[target_ticker]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재 주가", f"${report_data['price']:.2f}")
        col2.metric("PER", report_data['pe'])
        col3.metric("20일 이동평균", f"${report_data['ma20']:.2f}")
        col4.metric("RSI (투자심리)", f"{report_data['rsi']:.1f}")
        
        # 저장된 뉴스 출력
        st.markdown("---")
        st.subheader("📰 최근 주요 뉴스")
        for news in report_data['news']:
            st.markdown(f"- [{news['title']}]({news['link']})")
        
        st.plotly_chart(report_data['gauge_chart'], use_container_width=True)
        st.subheader("🤖 분석 보고서")
        st.write(report_data['ai_report'])

    # 새로 API를 호출하여 분석하기
    else:
        if not api_key:
            st.warning("API 키를 입력해 주세요.")
        else:
            try:
                st.info(f"{target_ticker} 실시간 데이터 수집 및 분석 중...")
                time.sleep(0.5)
                stock = yf.Ticker(target_ticker)
                hist = stock.history(period="3mo")
                
                if hist.empty:
                    st.error("데이터를 가져오지 못했습니다. 티커를 확인해 주세요.")
                else:
                    current_price = hist['Close'].iloc[-1]
                    info = stock.info
                    pe_ratio = info.get('trailingPE', '데이터 없음(N/A)')
                    
                    # 퀀트 지표 계산
                    ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    delta = hist['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]
                    
                    # [버그 수정] 뉴스 수집 및 화면 출력용 데이터 조립
                    news_list = stock.news
                    news_data_for_ui = [] 
                    if news_list:
                        for news in news_list[:5]:
                            title = "뉴스 제목 없음"
                            link = news.get('link', '#')
                            
                            if 'title' in news: 
                                title = news['title']
                            elif 'content' in news and 'title' in news['content']: 
                                title = news['content']['title']
                                if 'link' in news['content']:
                                    link = news['content']['link']
                                    
                            if link != '#' and not link.startswith('http'):
                                link = f"https://finance.yahoo.com{link}"
                                
                            news_data_for_ui.append({"title": title, "link": link})
                            
                    raw_headlines_text = "\n".join([f"- {n['title']}" for n in news_data_for_ui])
                    
                    # 게이지 차트 생성 (폰트 강제 통일 적용)
                    fig = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = current_rsi,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "RSI 투자 심리도 (30이하: 과매도/매수찬스, 70이상: 과매수/매도경고)"},
                        gauge = {
                            'axis': {'range': [0, 100]},
                            'bar': {'color': "black"},
                            'steps': [
                                {'range': [0, 30], 'color': "lightgreen"},
                                {'range': [30, 70], 'color': "lightgray"},
                                {'range': [70, 100], 'color': "salmon"}],
                        }
                    ))
                    fig.update_layout(font=dict(family="Pretendard, sans-serif")) # 차트 폰트 적용
                    
                    # AI 분석 실행
                    genai.configure(api_key=api_key)
                    model_name = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods][0]
                    model = genai.GenerativeModel(model_name)
                    
                    prompt = f"""
                    너는 데이터 기반의 월스트리트 AI 퀀트 애널리스트야.
                    [실제 근거 데이터]
                    - 종목: {target_ticker}
                    - 현재가: ${current_price:.2f}
                    - 20일 이동평균선: ${ma20:.2f} 
                    - 14일 RSI: {current_rsi:.1f}
                    - 최근 뉴스: {raw_headlines_text}

                    위 정량적 수치와 뉴스를 종합하여 다음 항목을 한국어로 작성해:
                    1. 📈 기술적 예측: 이동평균선과 RSI 수치를 해석하여 단기 주가 방향성 예측
                    2. 🌡️ 펀더멘털 & 감성: 뉴스와 시장 상황을 기반으로 한 요약
                    3. 💡 최종 매수/매도 전략: (목표 매수/매도가를 달러 숫자로 명확히 제시)
                    """
                    
                    response = model.generate_content(prompt)
                    ai_report = response.text
                    
                    # 세션에 데이터 완벽 저장
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.saved_reports[target_ticker] = {
                        'time': current_time,
                        'price': current_price,
                        'pe': pe_ratio,
                        'ma20': ma20,
                        'rsi': current_rsi,
                        'news': news_data_for_ui, # 수집된 뉴스도 저장!
                        'gauge_chart': fig,
                        'ai_report': ai_report
                    }
                    
                    # 화면 출력
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("현재 주가", f"${current_price:.2f}")
                    col2.metric("PER", pe_ratio)
                    col3.metric("20일 이동평균", f"${ma20:.2f}")
                    col4.metric("RSI (투자심리)", f"{current_rsi:.1f}")
                    
                    st.markdown("---")
                    st.subheader("📰 최근 주요 뉴스")
                    for news in news_data_for_ui:
                        st.markdown(f"- [{news['title']}]({news['link']})")
                    
                    st.plotly_chart(fig, use_container_width=True)
                    st.subheader("🤖 AI 분석 & 예측 보고서")
                    st.write(ai_report)
                    st.success(f"{target_ticker} 분석 완료 및 임시 보관함에 저장되었습니다!")

            except Exception as e:
                st.error(f"오류 발생: {e}")

# 실행이 끝난 후 강제 새로고침 플래그 초기화
st.session_state.force_refresh = False