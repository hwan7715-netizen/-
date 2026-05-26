import streamlit as st
import yfinance as yf
import google.generativeai as genai
import time
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(layout="wide") 
st.title("📊 주식 분석 대시보드")
st.markdown("---")

# --- [상태 저장소 초기화] ---
# 사용자가 분석한 데이터를 임시로 저장해두는 메모리 공간 생성
if 'saved_reports' not in st.session_state:
    st.session_state.saved_reports = {}

api_key = st.text_input("발급받은 Gemini API 키를 입력하세요:", type="password")

# --- [사이드바: 내 관심 종목 저장소] ---
with st.sidebar:
    st.header("📁 내 관심 종목)")
    st.write("분석한 종목은 브라우저를 닫기 전까지 이곳에 임시 저장합니다.")
    
    # 저장된 종목이 있을 경우 버튼을 생성하여 과거 데이터 바로 보기 지원
    if st.session_state.saved_reports:
        for saved_ticker, data in st.session_state.saved_reports.items():
            st.markdown(f"**{saved_ticker}** (최근 분석: {data['time']})")
            
            col_view, col_refresh = st.columns(2)
            with col_view:
                if st.button(f"보관함 보기", key=f"view_{saved_ticker}"):
                    st.session_state.current_view = saved_ticker
            with col_refresh:
                if st.button(f"🔄 최신화", key=f"refresh_{saved_ticker}"):
                    st.session_state.current_view = saved_ticker
                    st.session_state.force_refresh = True # 강제 업데이트 플래그
    else:
        st.info("아직 분석/저장된 종목이 없습니다.")

# 메인 검색창
ticker_input = st.text_input("분석할 미국 주식 티커 (예: AAPL, TSLA):").upper()

# 분석 실행 조건 설정 (새로 검색했거나, 사이드바에서 최신화 버튼을 눌렀을 때)
run_analysis = st.button("새 종목 분석 시작")
force_refresh = st.session_state.get('force_refresh', False)

target_ticker = ticker_input if run_analysis else st.session_state.get('current_view', None)

if target_ticker:
    # 이미 저장된 데이터가 있고, 강제 최신화가 아니라면 저장된 데이터 불러오기 (토큰 절약)
    if target_ticker in st.session_state.saved_reports and not run_analysis and not force_refresh:
        st.success(f"저장된 {target_ticker} 분석 데이터를 불러왔습니다. (데이터 기준일: {st.session_state.saved_reports[target_ticker]['time']})")
        report_data = st.session_state.saved_reports[target_ticker]
        
        # 화면에 저장된 지표와 차트 렌더링
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재 주가", f"${report_data['price']:.2f}")
        col2.metric("PER", report_data['pe'])
        col3.metric("20일 이동평균", f"${report_data['ma20']:.2f}")
        col4.metric("RSI (투자심리)", f"{report_data['rsi']:.1f}")
        
        st.plotly_chart(report_data['gauge_chart'], use_container_width=True)
        st.subheader("🤖 분석 보고서")
        st.write(report_data['ai_report'])

    # 저장된 데이터가 없거나, 분석/최신화 버튼을 눌렀을 때 (API 호출)
    else:
        if not api_key:
            st.warning("API 키를 입력해 주세요.")
        else:
            try:
                st.info(f"{target_ticker} 실시간 데이터 수집 및 분석 중...")
                time.sleep(0.5)
                stock = yf.Ticker(target_ticker)
                hist = stock.history(period="3mo") # 20일선 및 RSI 계산을 위해 3개월치 데이터 확보
                
                if hist.empty:
                    st.error("데이터를 가져오지 못했습니다. 티커를 확인해 주세요.")
                else:
                    current_price = hist['Close'].iloc[-1]
                    info = stock.info
                    pe_ratio = info.get('trailingPE', '데이터 없음(N/A)')
                    
                    # [기술적 지표 계산: 예측의 근거]
                    # 1. 20일 이동평균선 (최근 20일 종가 평균)
                    ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    
                    # 2. RSI (상대강도지수) 계산 공식
                    delta = hist['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]
                    
                    # 뉴스 수집 (최대 5개)
                    news_list = stock.news
                    news_data = [] 
                    if news_list:
                        for news in news_list[:5]:
                            title = "뉴스 제목 없음"
                            if 'title' in news: title = news['title']
                            elif 'content' in news and 'title' in news['content']: title = news['content']['title']
                            news_data.append(title)
                    raw_headlines_text = "\n".join([f"- {n}" for n in news_data])
                    
                    # [시각화] Plotly를 이용한 RSI 투자 심리 게이지 차트 생성
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
                    
                    # AI 예측 프롬프트 설정 (계산된 퀀트 지표 주입)
                    genai.configure(api_key=api_key)
                    model_name = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods][0]
                    model = genai.GenerativeModel(model_name)
                    
                    prompt = f"""
                    너는 데이터 기반의 월스트리트 AI 퀀트 애널리스트야.
                    [실제 근거 데이터]
                    - 종목: {target_ticker}
                    - 현재가: ${current_price:.2f}
                    - 20일 이동평균선: ${ma20:.2f} (현재가가 이보다 낮으면 하락추세, 높으면 상승추세)
                    - 14일 RSI: {current_rsi:.1f} (30 이하는 저평가/반등예측, 70 이상은 고평가/하락예측)
                    - 최근 뉴스: {raw_headlines_text}

                    위 정량적 수치와 뉴스를 종합하여 다음 항목을 작성해:
                    1. 📈 기술적 예측: 이동평균선과 RSI 수치를 해석하여 단기 주가 방향성 예측
                    2. 🌡️ 펀더멘털 & 감성: 뉴스와 시장 상황을 기반으로 한 요약
                    3. 💡 최종 매수/매도 전략: (목표 매수/매도가를 달러 숫자로 명확히 제시)
                    """
                    
                    response = model.generate_content(prompt)
                    ai_report = response.text
                    
                    # 데이터 저장소(세션)에 현재 분석 결과와 시간 기록 (데이터 캐싱)
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.saved_reports[target_ticker] = {
                        'time': current_time,
                        'price': current_price,
                        'pe': pe_ratio,
                        'ma20': ma20,
                        'rsi': current_rsi,
                        'gauge_chart': fig,
                        'ai_report': ai_report
                    }
                    
                    # 분석 직후 화면 렌더링
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("현재 주가", f"${current_price:.2f}")
                    col2.metric("PER", pe_ratio)
                    col3.metric("20일 이동평균", f"${ma20:.2f}")
                    col4.metric("RSI (투자심리)", f"{current_rsi:.1f}")
                    
                    st.plotly_chart(fig, use_container_width=True)
                    st.subheader("🤖 AI 분석 & 예측 보고서")
                    st.write(ai_report)
                    st.success(f"{target_ticker} 분석 완료 및 임시 보관함에 저장되었습니다!")

            except Exception as e:
                st.error(f"오류 발생: {e}")

# 강제 최신화 플래그 초기화 (무한 루프 방지)
if 'force_refresh' in st.session_state:
    st.session_state.force_refresh = False