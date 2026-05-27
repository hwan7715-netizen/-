import streamlit as st
import yfinance as yf
import google.generativeai as genai
import time
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

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

st.title("📊 AI 퀀트 주식 분석 대시보드 (Ultimate)")
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
    if target_ticker in st.session_state.saved_reports and not force_refresh:
        st.success(f"📌 임시 보관함에서 {target_ticker} 데이터를 불러왔습니다. (데이터 기준: {st.session_state.saved_reports[target_ticker]['time']})")
        report_data = st.session_state.saved_reports[target_ticker]
        
        # [수정] 핵심 지표 5개로 확장 (EPS 추가)
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("현재 주가", f"${report_data['price']:.2f}")
        col2.metric("PER (수익비율)", report_data['pe'])
        col3.metric("EPS (주당순이익)", report_data['eps'])
        col4.metric("20일 이동평균", f"${report_data['ma20']:.2f}")
        col5.metric("RSI (투자심리)", f"{report_data['rsi']:.1f}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.plotly_chart(report_data['line_chart'], use_container_width=True)
        with chart_col2:
            st.plotly_chart(report_data['gauge_chart'], use_container_width=True)
        
        st.markdown("---")
        news_col, report_col = st.columns([1, 2])
        
        with news_col:
            st.subheader("📰 최근 주요 뉴스")
            for news in report_data['news']:
                st.markdown(f"- [{news['title']}]({news['link']})")
            
        with report_col:
            st.subheader("🤖 AI 퀀트 심층 보고서")
            with st.container(border=True): 
                st.write(report_data['ai_report'])

    else:
        if not api_key:
            st.warning("API 키를 입력해 주세요.")
        else:
            try:
                st.info(f"{target_ticker} 실시간 데이터를 수집하고 AI 심층 분석을 진행합니다. 잠시만 기다려주세요...")
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
                    
                    # [신규] EPS 데이터 추출
                    eps_raw = info.get('trailingEps', info.get('forwardEps'))
                    eps_value = f"${eps_raw:.2f}" if eps_raw else "N/A"
                    
                    ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    delta = hist['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]
                    
                    # [신규] 거래량 상태 분석
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].mean()
                    volume_status = "급증" if current_volume > avg_volume * 1.5 else ("감소" if current_volume < avg_volume * 0.8 else "평이")
                    
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
                            
                            if not link.startswith('http'):
                                if link.startswith('/'): link = f"https://finance.yahoo.com{link}"
                                else: link = f"https://finance.yahoo.com/quote/{target_ticker}/news"
                            news_data_for_ui.append({"title": title, "link": link})
                            
                    raw_headlines_text = "\n".join([f"- {n['title']}" for n in news_data_for_ui])
                    
                    # [신규] 2단 분할 차트 생성 (주가+추세선 / 거래량)
                    line_fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                    
                    # 1. 주가 선 (상단)
                    line_fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name='주가', line=dict(color='#1E88E5', width=2)), row=1, col=1)
                    
                    # 2. 선형 회귀 추세선 (상단)
                    x_data = np.arange(len(hist))
                    y_data = hist['Close'].values
                    z = np.polyfit(x_data, y_data, 1)
                    p = np.poly1d(z)
                    line_fig.add_trace(go.Scatter(x=hist.index, y=p(x_data), mode='lines', name='추세선', line=dict(color='#EF5350', width=2, dash='dot')), row=1, col=1)
                    
                    # 3. 거래량 바 차트 (하단) - 전일 대비 등락에 따라 색상 변경
                    vol_colors = ['#EF5350' if row['Open'] > row['Close'] else '#26A69A' for index, row in hist.iterrows()]
                    line_fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='거래량', marker_color=vol_colors), row=2, col=1)
                    
                    line_fig.update_layout(title="📈 최근 3개월 주가 흐름 및 거래량", margin=dict(l=0, r=0, t=40, b=0), font=dict(family="Pretendard"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
                    
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
                    
                    # [수정] 프롬프트에 EPS 및 거래량 데이터 주입
                    genai.configure(api_key=api_key)
                    model_name = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods][0]
                    model = genai.GenerativeModel(model_name)
                    
                    prompt = f"""
                    너는 월스트리트 최고의 시니어 퀀트 애널리스트야.
                    [실제 데이터] 
                    - 종목: {target_ticker} / 현재가: ${current_price:.2f} 
                    - 펀더멘털: EPS {eps_value} / PER {pe_ratio}
                    - 기술적 지표: 20일 이평선 ${ma20:.2f} / RSI {current_rsi:.1f}
                    - 거래량 상태: 최근 평균 대비 [{volume_status}] 상태
                    [최근 뉴스]: {raw_headlines_text}

                    위 데이터를 종합하여 초보자도 이해하기 쉽지만, 내용의 깊이가 있는 전문가 수준의 투자 리포트를 작성해.
                    가독성을 위해 반드시 아래의 양식과 [글머리 기호(-)]를 사용하여 구조화된 형태로 작성할 것.

                    ### 1. 📈 기술적 지표 심층 분석
                    - 추세(이평선)와 투자심리(RSI)를 분석해.
                    - 최근 거래량의 변화({volume_status})가 주가의 상승/하락 신호에 어떤 의미를 주는지 해석해.

                    ### 2. 🌡️ 펀더멘털 및 시장 모멘텀
                    - 기업의 수익성(EPS/PER)을 평가하고 현재 가격이 합리적인지 분석해.
                    - 제공된 뉴스를 바탕으로 한 단기 호재/악재와 향후 촉매제를 적어줘.

                    ### 3. 🎯 월스트리트 AI 최종 투자 전략
                    - **전략 방향:** (적극 매수 / 분할 매수 / 관망 / 분할 매도 / 적극 매도 중 1개 선택)
                    - **목표 매수가:** $000 ~ $000
                    - **목표 매도가:** $000 ~ $000
                    - **핵심 요약:** (현재 상황에 대한 전문가의 통찰력 있는 1~2줄 평)
                    """
                    
                    response = model.generate_content(prompt)
                    ai_report = response.text
                    
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.saved_reports[target_ticker] = {
                        'time': current_time,
                        'price': current_price,
                        'pe': pe_ratio,
                        'eps': eps_value,
                        'ma20': ma20,
                        'rsi': current_rsi,
                        'news': news_data_for_ui,
                        'line_chart': line_fig,
                        'gauge_chart': gauge_fig,
                        'ai_report': ai_report
                    }
                    
                    st.session_state.force_refresh = False
                    st.rerun()

            except Exception as e:
                st.error(f"오류 발생: {e}")