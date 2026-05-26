import streamlit as st
import yfinance as yf
import google.generativeai as genai

# 웹사이트를 넓게 쓰도록 대시보드 형태로 설정
st.set_page_config(layout="wide") 
st.title("📊 AI 퀀트 주식 대시보드 (Pro 버전)")
st.markdown("---")

api_key = st.text_input("발급받은 Gemini API 키를 입력하세요:", type="password")
ticker = st.text_input("분석할 미국 주식 티커 (예: AAPL, TSLA, NVDA):")

if st.button("심층 분석 시작"):
    if not api_key or not ticker:
        st.warning("API 키와 티커를 모두 입력해 주세요.")
    else:
        try:
            # 1. 근거 데이터 수집 파이프라인
            st.info("데이터 수집 중: 실시간 주가, 핵심 재무 지표, 최신 뉴스를 가져옵니다...")
            stock = yf.Ticker(ticker)
            
            # 주가 및 재무 데이터 가져오기
            hist = stock.history(period="1mo")
            current_price = hist['Close'].iloc[-1]
            info = stock.info
            pe_ratio = info.get('trailingPE', '데이터 없음(N/A)')
            
            # 시가총액 계산
            market_cap_raw = info.get('marketCap', 0)
            market_cap = f"{market_cap_raw / 1000000000:.2f}B USD" if market_cap_raw else "데이터 없음"
            
            # [오류 해결 부분] 최신 뉴스 데이터 구조 변경에 대응하는 방어적 코드
            news_list = stock.news
            news_headlines = []
            if news_list:
                for news in news_list[:5]:
                    # 예전 방식의 데이터 구조일 경우
                    if 'title' in news:
                        news_headlines.append(news['title'])
                    # 최근 변경된 데이터 구조일 경우 (content 안에 숨어있음)
                    elif 'content' in news and 'title' in news['content']:
                        news_headlines.append(news['content']['title'])
                    else:
                        news_headlines.append("뉴스 제목을 파싱할 수 없습니다.")
            else:
                news_headlines = ["최근 뉴스 데이터가 없습니다."]
                
            news_text = "\n".join(news_headlines)

            # 2. 대시보드 화면 구성
            col1, col2, col3 = st.columns(3)
            col1.metric("현재 주가", f"${current_price:.2f}")
            col2.metric("PER (주가수익비율)", f"{pe_ratio}")
            col3.metric("시가총액", market_cap)

            st.write("")
            st.subheader("📰 최근 주요 뉴스 헤드라인")
            for headline in news_headlines:
                st.write(f"- {headline}")
            
            st.markdown("---")
            
            # 3. 수집된 근거를 바탕으로 AI 심층 분석 요청
            st.info("수집된 실제 데이터를 바탕으로 AI가 투자 논리를 구성하고 있습니다...")
            genai.configure(api_key=api_key)
            
            target_model_name = None
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    target_model_name = m.name
                    break 
            
            model = genai.GenerativeModel(target_model_name)
            
            prompt = f"""
            너는 월스트리트 최고의 AI 퀀트 애널리스트야.
            아래에 제공된 {ticker} 기업의 실제 데이터를 철저히 분석해서 보고서를 작성해 줘. 
            단순히 뻔한 소리를 하지 말고, 제공된 데이터를 근거로 논리적인 주장을 펼쳐야 해.

            [실제 근거 데이터]
            - 현재가: ${current_price}
            - PER (주가수익비율): {pe_ratio}
            - 최근 최신 뉴스 헤드라인:
            {news_text}

            위 데이터를 바탕으로 다음 4가지 항목을 마크다운 양식으로 명확히 작성해 줘:
            1. 📊 펀더멘털 평가: (PER 등 지표를 기반으로 한 현재 가격 고평가/저평가 여부)
            2. 🌡️ 시장 감성 분석: (뉴스를 기반으로 한 시장의 긍정/부정/중립 분위기 판단과 그 이유)
            3. 🎯 매수/매도 전략: (현재가와 감성을 종합한 구체적인 추천 가격대와 논리적 근거 제시)
            4. 🔗 밸류체인 수혜주: (이 기업의 흐름에 영향을 받는 관련 수혜주 2개와 그 이유)
            """
            
            response = model.generate_content(prompt)
            
            # AI 분석 결과 출력
            st.subheader("🤖 AI 퀀트 심층 분석 보고서")
            st.write(response.text)
            
            st.caption("주의: 본 정보는 AI 분석에 의한 참고 자료이며, 투자 결과에 대한 법적 책임은 투자자 본인에게 있습니다.")

        except Exception as e:
            st.error(f"데이터를 불러오는 중 오류가 발생했습니다. (에러 내용: {e})")