import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pandas as pd
import FinanceDataReader as fdr
import re 
import requests
from bs4 import BeautifulSoup

# 1. 웹 페이지 기본 설정
st.set_page_config(page_title="주가 분석 대시보드", layout="wide")

# UI 글자 크기 커스텀 CSS 주입
st.markdown("""
<style>
    h3 { font-size: 1.3rem !important; padding-bottom: 0.2rem !important; }
    div[data-testid="stMetricLabel"] > label > div { font-size: 0.85rem !important; }
    div[data-testid="stMetricValue"] > div { font-size: 1.6rem !important; }
</style>
""", unsafe_allow_html=True)

# 2. 한국 거래소 실시간 종목 리스트 로딩 (캐싱)
@st.cache_data
def get_krx_stocks():
    return fdr.StockListing('KRX')

df_krx = get_krx_stocks()

# 3. 사이드바: 사용자 설정
st.sidebar.header("🔍 분석 조건 설정")
user_input = st.sidebar.text_input(
    "종목명, 코드 또는 티커 입력", value="", 
    help="한글 종목명, 6자리 코드, 또는 미국 주식 티커(예: AAPL)를 입력하세요."
)

# 수정된 부분: 초기 조회 시작일을 365일(1년)로 변경
start_date = st.sidebar.date_input("조회 시작일", value=datetime.today() - timedelta(days=365))
end_date = st.sidebar.date_input("조회 종료일", value=datetime.today())

st.sidebar.markdown("---")
st.sidebar.header("📈 보조지표 설정")
indicator_choice = st.sidebar.radio("하단 차트에 추가할 지표를 선택하세요", ["선택 안 함", "RSI (과열/침체)", "MACD (추세강도)"])

st.sidebar.markdown("---")
st.sidebar.header("⚖️ 시장 지수 비교")
compare_index = st.sidebar.checkbox("벤치마크 지수 배경에 표시", value=True)

# 헬퍼 함수 1: 미국 주식 시가총액 단위 변환
def format_market_cap_us(value):
    if pd.isna(value) or value is None or value == 'N/A':
        return "N/A"
    try:
        value = float(value)
        if value >= 1e12: return f"${value/1e12:.2f}T (조 달러)"
        elif value >= 1e9: return f"${value/1e9:.2f}B (십억 달러)"
        else: return f"${value:,.0f}"
    except:
        return "N/A"

# 헬퍼 함수 2: 네이버 금융 크롤링 (timeout 추가로 안정성 확보)
@st.cache_data(ttl=3600) 
def get_naver_finance_info(code):
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    info = {'market_cap': 'N/A', 'per': 'N/A', 'pbr': 'N/A', 'dividend': 'N/A'}
    
    try:
        # timeout=5 를 추가하여 5초 이상 응답 없으면 예외 처리
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        market_sum = soup.select_one('#_market_sum')
        if market_sum: info['market_cap'] = market_sum.text.strip() + "억 원"

        per = soup.select_one('#_per')
        if per: info['per'] = per.text.strip() + "배"

        pbr = soup.select_one('#_pbr')
        if pbr: info['pbr'] = pbr.text.strip() + "배"

        dvr = soup.select_one('#_dvr')
        if dvr: info['dividend'] = dvr.text.strip() + "%"
            
    except Exception:
        pass 
    return info

# 4. 데이터 조회 로직
if st.sidebar.button("📊 실시간 차트 생성"):
    target_ticker = user_input.strip()
    
    if not target_ticker:
        st.error("⚠️ 종목명, 종목코드 또는 미국 티커를 입력해주세요.")
    else:
        is_us_stock = bool(re.match(r'^[a-zA-Z]+$', target_ticker))
        
        search_code = ""
        final_ticker = ""
        
        if is_us_stock:
            final_ticker = target_ticker.upper()
            st.success(f"🌎 미국 주식 티커로 인식했습니다: {final_ticker}")
        else:
            if not target_ticker.isdigit():
                match = df_krx[df_krx['Name'] == target_ticker]
                if not match.empty:
                    search_code = match['Code'].values[0]
                    st.success(f"✅ [{target_ticker}] 종목 코드를 찾았습니다: {search_code}")
                else:
                    st.error(f"'{target_ticker}'에 해당하는 종목을 리스트에서 찾을 수 없습니다.")
            else:
                search_code = target_ticker
                
            if search_code:
                final_ticker = f"{search_code}.KS"
        
        if final_ticker:
            display_name = final_ticker if is_us_stock else f"{search_code}.KS/KQ"
            st.info(f"데이터 허브에서 [{display_name}] 자산을 동기화 중입니다...")
            
            try:
                ticker_obj = yf.Ticker(final_ticker)
                data = ticker_obj.history(start=start_date, end=end_date)
                
                is_kosdaq = False
                if data.empty and not is_us_stock:
                    final_ticker = f"{search_code}.KQ"
                    ticker_obj = yf.Ticker(final_ticker)
                    data = ticker_obj.history(start=start_date, end=end_date)
                    is_kosdaq = True
                
                if data.empty:
                    st.error("데이터를 불러올 수 없습니다. 상장 폐지 여부나 최근 거래 정지 여부를 확인해 주세요.")
                else:
                    close_price = data['Close'].squeeze()
                    open_price = data['Open'].squeeze()
                    high_price = data['High'].squeeze()
                    low_price = data['Low'].squeeze()
                    volume = data['Volume'].squeeze()

                    data['MA20'] = close_price.rolling(window=20).mean()
                    data['MA60'] = close_price.rolling(window=60).mean()
                    data['MA120'] = close_price.rolling(window=120).mean()
                    
                    delta = close_price.diff()
                    gain = delta.where(delta > 0, 0).ewm(com=13, adjust=False).mean()
                    loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
                    rs = gain / loss
                    data['RSI'] = 100 - (100 / (1 + rs))
                    
                    exp1 = close_price.ewm(span=12, adjust=False).mean()
                    exp2 = close_price.ewm(span=26, adjust=False).mean()
                    data['MACD'] = exp1 - exp2
                    data['Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
                    data['MACD_Hist'] = data['MACD'] - data['Signal']
                    
                    idx_data = pd.DataFrame()
                    benchmark_name = ""
                    if compare_index:
                        if is_us_stock:
                            benchmark_ticker, benchmark_name = "^GSPC", "S&P 500"
                        elif is_kosdaq:
                            benchmark_ticker, benchmark_name = "^KQ11", "KOSDAQ"
                        else:
                            benchmark_ticker, benchmark_name = "^KS11", "KOSPI"
                        idx_data = yf.download(benchmark_ticker, start=start_date, end=end_date, progress=False)

                    num_rows = 3 if indicator_choice != "선택 안 함" else 2
                    row_heights = [0.6, 0.2, 0.2] if num_rows == 3 else [0.7, 0.3]
                    chart_height = 900 if num_rows == 3 else 800
                    
                    specs = [[{"secondary_y": True}]] + [[{"secondary_y": False}]] * (num_rows - 1)
                    fig = make_subplots(rows=num_rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights, specs=specs)
                    
                    currency_sym = "$" if is_us_stock else ""
                    currency_unit = "" if is_us_stock else "원"
                    p_format = ",.2f" if is_us_stock else ",.0f" 
                    
                    custom_hover_text = [
                        f"<b>{d.strftime('%Y-%m-%d')}</b><br><br>시가: {currency_sym}{o:{p_format}}{currency_unit}<br>최고: {currency_sym}{h:{p_format}}{currency_unit}<br>최저: {currency_sym}{l:{p_format}}{currency_unit}<br>종가: {currency_sym}{c:{p_format}}{currency_unit}"
                        for d, o, h, l, c in zip(data.index, open_price, high_price, low_price, close_price)
                    ]
                    
                    fig.add_trace(go.Candlestick(x=data.index, open=open_price, high=high_price, low=low_price, close=close_price, name="주가", increasing_line_color='red', decreasing_line_color='blue', text=custom_hover_text, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=1, col=1, secondary_y=False)
                    fig.add_trace(go.Scatter(x=data.index, y=data['MA20'].squeeze(), mode='lines', name='20일선', line=dict(color='black', width=1.5)), row=1, col=1, secondary_y=False)
                    fig.add_trace(go.Scatter(x=data.index, y=data['MA60'].squeeze(), mode='lines', name='60일선', line=dict(color='orange', width=1.5)), row=1, col=1, secondary_y=False)
                    fig.add_trace(go.Scatter(x=data.index, y=data['MA120'].squeeze(), mode='lines', name='120일선', line=dict(color='red', width=2)), row=1, col=1, secondary_y=False)
                    
                    if compare_index and not idx_data.empty:
                        idx_close = idx_data['Close'].squeeze()
                        idx_hover = [f"<b>{d.strftime('%Y-%m-%d')}</b><br>{benchmark_name}: {v:,.2f}" for d, v in zip(idx_data.index, idx_close)]
                        fig.add_trace(go.Scatter(x=idx_data.index, y=idx_close, mode='lines', name=benchmark_name, line=dict(color='rgba(65, 105, 225, 0.85)', width=2.5, dash='dot'), text=idx_hover, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=1, col=1, secondary_y=True)
                        fig.update_yaxes(title_text=f"{benchmark_name}", showgrid=False, secondary_y=True, row=1, col=1)

                    volume_colors = ['red' if c >= o else 'blue' for c, o in zip(close_price, open_price)]
                    volume_hover_text = [f"<b>{d.strftime('%Y-%m-%d')}</b><br>거래량: {v:,.0f}주" for d, v in zip(data.index, volume)]
                    fig.add_trace(go.Bar(x=data.index, y=volume, name="거래량", marker_color=volume_colors, showlegend=False, text=volume_hover_text, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=2, col=1)
                    
                    if indicator_choice == "RSI (과열/침체)":
                        rsi_hover = [f"<b>{d.strftime('%Y-%m-%d')}</b><br>RSI: {v:.2f}" for d, v in zip(data.index, data['RSI'].squeeze())]
                        fig.add_trace(go.Scatter(x=data.index, y=data['RSI'].squeeze(), mode='lines', name='RSI', line=dict(color='purple', width=1.5), text=rsi_hover, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=3, col=1)
                        fig.add_hline(y=70, line_dash="dash", line_color="red", line_width=1, row=3, col=1)
                        fig.add_hline(y=30, line_dash="dash", line_color="blue", line_width=1, row=3, col=1)
                        fig.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
                    elif indicator_choice == "MACD (추세강도)":
                        macd, signal, macd_hist = data['MACD'].squeeze(), data['Signal'].squeeze(), data['MACD_Hist'].squeeze()
                        hist_colors = ['red' if val > 0 else 'blue' for val in macd_hist]
                        hist_hover = [f"<b>{d.strftime('%Y-%m-%d')}</b><br>MACD Hist: {v:.3f}" for d, v in zip(data.index, macd_hist)]
                        macd_hover = [f"<b>{d.strftime('%Y-%m-%d')}</b><br>MACD: {v:.3f}" for d, v in zip(data.index, macd)]
                        signal_hover = [f"<b>{d.strftime('%Y-%m-%d')}</b><br>Signal: {v:.3f}" for d, v in zip(data.index, signal)]
                        fig.add_trace(go.Bar(x=data.index, y=macd_hist, name='MACD Hist', marker_color=hist_colors, text=hist_hover, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=3, col=1)
                        fig.add_trace(go.Scatter(x=data.index, y=macd, mode='lines', name='MACD', line=dict(color='black', width=1.5), text=macd_hover, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=3, col=1)
                        fig.add_trace(go.Scatter(x=data.index, y=signal, mode='lines', name='Signal', line=dict(color='orange', width=1.5), text=signal_hover, hoverinfo="text", hovertemplate="%{text}<extra></extra>"), row=3, col=1)
                        fig.update_yaxes(title_text="MACD", row=3, col=1)

                    years = data.index.year.unique()
                    for y in years:
                        year_data = data[data.index.year == y]
                        if not year_data.empty:
                            start_d = year_data.index[0]
                            mid_d = start_d + (year_data.index[-1] - start_d) / 2
                            fig.add_annotation(x=mid_d, y=1.05, yref='paper', showarrow=False, text=f"<b>| ◀ {y}년도 ▶ |</b>", font=dict(size=14, color="gray"))
                            if start_d > data.index[0]:
                                fig.add_vline(x=start_d, line_dash="dash", line_color="gray", opacity=0.5)

                    fig.update_layout(title=f"<b>{target_ticker.upper()} ({final_ticker}) 통합 분석</b>", template="plotly_white", height=chart_height, margin=dict(t=120), hoverlabel=dict(bgcolor="white", font_color="black", font_size=13), showlegend=False)
                    fig.update_yaxes(title_text=f"가격 ({'USD' if is_us_stock else 'KRW'})", tickformat=p_format, row=1, col=1, secondary_y=False)
                    fig.update_yaxes(title_text="거래량", tickformat=",.0f", row=2, col=1)
                    fig.update_xaxes(tickformat="%m.%d", nticks=30, tickangle=-45, showgrid=True, gridcolor='rgba(211, 211, 211, 0.7)', gridwidth=1, rangeslider_visible=False)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # --- [1] 가격 지표 ---
                    current_price = float(close_price.iloc[-1])
                    highest_price = float(high_price.max())
                    lowest_price = float(low_price.min())  
                    mdd = ((current_price - highest_price) / highest_price) * 100
                    
                    st.markdown("### 📊 가격 지표")
                    spacer, col1, col2, col3, col4 = st.columns([0.1, 1, 1, 1, 1])
                    with col1: st.metric("현재가", f"{currency_sym}{current_price:{p_format}} {currency_unit}".strip())
                    with col2: st.metric("최고가", f"{currency_sym}{highest_price:{p_format}} {currency_unit}".strip())
                    with col3: st.metric("최저가", f"{currency_sym}{lowest_price:{p_format}} {currency_unit}".strip())
                    with col4: st.metric("MDD", f"{mdd:.2f}%")
                        
                    # --- [2] 펀더멘털 요약 지표 ---
                    st.markdown("---")
                    st.markdown("### 🏢 기업 펀더멘털 요약")
                    
                    if is_us_stock:
                        info = ticker_obj.info
                        market_cap = info.get('marketCap', 'N/A')
                        trailing_pe = info.get('trailingPE', 'N/A')
                        price_to_book = info.get('priceToBook', 'N/A')
                        dividend_yield = info.get('dividendYield', 'N/A')
                        
                        mc_display = format_market_cap_us(market_cap)
                        div_display = f"{dividend_yield * 100:.2f}%" if dividend_yield not in ['N/A', None] else "N/A"
                        pe_display = f"{trailing_pe:.2f}배" if trailing_pe not in ['N/A', None] else "N/A"
                        pb_display = f"{price_to_book:.2f}배" if price_to_book not in ['N/A', None] else "N/A"
                    else:
                        naver_info = get_naver_finance_info(search_code)
                        mc_display = naver_info['market_cap']
                        pe_display = naver_info['per']
                        pb_display = naver_info['pbr']
                        div_display = naver_info['dividend']
                    
                    f_spacer, f_col1, f_col2, f_col3, f_col4 = st.columns([0.1, 1, 1, 1, 1])
                    with f_col1: st.metric("시가총액", mc_display)
                    with f_col2: st.metric("PER (주가수익비율)", pe_display)
                    with f_col3: st.metric("PBR (주가순자산비율)", pb_display)
                    with f_col4: st.metric("배당수익률", div_display)
            
            except Exception as e:
                st.error(f"오류 발생: {e}")