import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import requests
from fpdf import FPDF
import scipy.stats as si
import scipy.optimize as sco

# ==========================================
# 1. PAGE CONFIGURATION & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="Titan Equity Terminal", page_icon="💼", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    h1, h2, h3 {color: #e2e8f0; font-family: 'Helvetica Neue', sans-serif;}
    .stMetric {background-color: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #334155; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
    .stTabs [data-baseweb="tab"] {font-size: 13px; font-weight: 600; color: #94a3b8; padding: 12px 16px;}
    .stTabs [data-baseweb="tab"][aria-selected="true"] {color: #3b82f6; border-bottom-color: #3b82f6;}
    .command-bar {background-color: #1e293b; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #3b82f6;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CORE ENGINE & MEMORY CACHING
# ==========================================
def resolve_automatic_peer(ticker, sector="", industry=""):
    tk = ticker.upper().strip()
    pairs_map = {
        "TCS.NS": "INFY.NS", "INFY.NS": "TCS.NS", "WIPRO.NS": "TCS.NS", "HCLTECH.NS": "INFY.NS",
        "BIOCON.NS": "DRREDDY.NS", "DRREDDY.NS": "CIPLA.NS", "CIPLA.NS": "SUNPHARMA.NS", "SUNPHARMA.NS": "CIPLA.NS",
        "TATAMOTORS.NS": "M&M.NS", "M&M.NS": "TATAMOTORS.NS", "MARUTI.NS": "M&M.NS",
        "RELIANCE.NS": "ONGC.NS", "HDFCBANK.NS": "ICICIBANK.NS", "ICICIBANK.NS": "HDFCBANK.NS", "SBIN.NS": "BOB.NS",
        "AAPL": "MSFT", "MSFT": "AAPL", "GOOG": "META", "META": "GOOG", "AMZN": "WMT", "KO": "PEP", "PEP": "KO"
    }
    if tk in pairs_map: return pairs_map[tk]
    sec, ind = sector.lower(), industry.lower()
    is_indian = ".NS" in tk or ".BO" in tk
    if "software" in ind or "it services" in ind or "technology" in sec: return "INFY.NS" if is_indian else "MSFT"
    if "pharma" in ind or "biotech" in ind or "health" in sec: return "CIPLA.NS" if is_indian else "PFE"
    if "bank" in ind or "finance" in sec: return "ICICIBANK.NS" if is_indian else "JPM"
    if "auto" in ind or "vehicle" in ind: return "M&M.NS" if is_indian else "F"
    return "INFY.NS" if is_indian else "AAPL"

@st.cache_data(ttl=300, show_spinner=False)
def get_search_candidates(query):
    clean_query = query.strip()
    if not clean_query: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={clean_query}"
    headers = {"User-Agent": "Mozilla/5.0"}
    candidates = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        if 'quotes' in data:
            for quote in data['quotes']:
                if quote.get('quoteType') in ['EQUITY', 'ETF', 'INDEX']:
                    name = quote.get('shortname', quote.get('longname', 'Unknown Name'))
                    symbol = quote.get('symbol', '')
                    exch = quote.get('exchange', 'Unknown Exchange')
                    candidates.append({"display": f"{name} ({symbol}) - {exch}", "symbol": symbol})
    except Exception: pass
    if not candidates:
        raw = clean_query.upper().replace(" ", "")
        candidates.append({"display": f"Exact Ticker Match: {raw}", "symbol": raw})
        if "." not in raw:
            candidates.append({"display": f"Indian Market Guess: {raw}.NS", "symbol": f"{raw}.NS"})
    return candidates

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market_data(ticker_symbol, time_horizon="1y"):
    try:
        df = yf.download(ticker_symbol, period=time_horizon, progress=False)
        if df.empty: return False, None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df = df.dropna().reset_index()
        
        date_col = 'Date' if 'Date' in df.columns else 'Datetime'
        df_market = pd.DataFrame({
            'date': pd.to_datetime(df[date_col]).dt.tz_localize(None),
            'close_price': df['Close'].astype(float),
            'volume': df['Volume'].astype(int),
            'sma_50': df['SMA_50'].astype(float),
            'sma_200': df['SMA_200'].astype(float)
        })
        return True, df_market
    except Exception:
        return False, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_peer_history(tickers_list, time_horizon="1y"):
    try:
        df = yf.download(tickers_list, period=time_horizon, progress=False)
        if df.empty: return pd.DataFrame()
        
        if isinstance(df.columns, pd.MultiIndex):
            if 'Close' in df.columns.get_level_values(0):
                return df['Close']
            elif 'Close' in df.columns.get_level_values(1):
                return df.xs('Close', level=1, axis=1)
        elif 'Close' in df.columns:
            res = df[['Close']].copy()
            res.columns = [tickers_list[0]]
            return res
        return pd.DataFrame()
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_macro_history(time_horizon="1y"):
    try:
        df = yf.download(['^TNX', '^IRX', '^VIX'], period=time_horizon, progress=False)
        if 'Close' in df.columns: return df['Close']
        return pd.DataFrame()
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_ticker_info(ticker):
    try: return yf.Ticker(ticker).info
    except: return {}

def extract_financial_statements(raw_ticker, info):
    metrics = {
        'revenue': info.get('totalRevenue'), 'net_income': info.get('netIncomeToCommon'), 
        'total_assets': info.get('totalAssets'), 'total_equity': info.get('totalStockholderEquity'), 
        'fcf': info.get('freeCashflow'), 'total_liabilities': info.get('totalLiabilitiesNetMinorityInterest'),
        'ebit': info.get('ebitda'), 'operating_cashflow': info.get('operatingCashflow'),
        'current_assets': None, 'current_liabilities': None
    }
    try:
        inc, bs, cf = raw_ticker.financials, raw_ticker.balance_sheet, raw_ticker.cashflow
        if not inc.empty and metrics['revenue'] is None:
            for k in ['Total Revenue', 'Operating Revenue', 'Revenue']:
                if k in inc.index: metrics['revenue'] = inc.loc[k].iloc[0]; break
        if not inc.empty and metrics['net_income'] is None:
            for k in ['Net Income', 'Net Income Common Stockholders']:
                if k in inc.index: metrics['net_income'] = inc.loc[k].iloc[0]; break
        if not bs.empty and metrics['total_assets'] is None:
            if 'Total Assets' in bs.index: metrics['total_assets'] = bs.loc['Total Assets'].iloc[0]
        if not bs.empty and metrics['total_equity'] is None:
            for k in ['Stockholders Equity', 'Common Stock Equity']:
                if k in bs.index: metrics['total_equity'] = bs.loc[k].iloc[0]; break
        if not bs.empty and metrics['total_liabilities'] is None:
            if 'Total Liabilities Net Minority Interest' in bs.index: metrics['total_liabilities'] = bs.loc['Total Liabilities Net Minority Interest'].iloc[0]
        if not cf.empty and metrics['fcf'] is None:
            if 'Free Cash Flow' in cf.index: metrics['fcf'] = cf.loc['Free Cash Flow'].iloc[0]
        if not cf.empty and metrics['operating_cashflow'] is None:
            if 'Operating Cash Flow' in cf.index: metrics['operating_cashflow'] = cf.loc['Operating Cash Flow'].iloc[0]
        if not bs.empty and metrics['current_assets'] is None:
            if 'Total Current Assets' in bs.index: metrics['current_assets'] = bs.loc['Total Current Assets'].iloc[0]
        if not bs.empty and metrics['current_liabilities'] is None:
            if 'Total Current Liabilities' in bs.index: metrics['current_liabilities'] = bs.loc['Total Current Liabilities'].iloc[0]
    except Exception: pass
    return metrics

def generate_pdf_report(ticker, full_name, sector, curr_sym, c_price, info, dcf_results, dupont, graham):
    pdf_sym = "INR " if curr_sym == "₹" else curr_sym
    safe_name = full_name.encode('latin-1', 'ignore').decode('latin-1')
    safe_sector = sector.encode('latin-1', 'ignore').decode('latin-1')
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"INSTITUTIONAL TEAR SHEET: {safe_name} ({ticker})", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Sector: {safe_sector}  |  Currency: {pdf_sym.strip()}", ln=True, align='C')
    pdf.line(10, 30, 200, 30)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Market Overview & Multiples", ln=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(95, 6, f"Current Trading Price: {pdf_sym}{c_price:.2f}")
    pdf.cell(95, 6, f"Systematic Risk (Beta): {info.get('beta', 'N/A')}", ln=True)
    pdf.cell(95, 6, f"Trailing P/E Ratio: {info.get('trailingPE', 'N/A')}x")
    pdf.cell(95, 6, f"Graham Number Intrinsic Value: {pdf_sym}{graham:.2f}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Intrinsic Valuation (DCF / DDM Scenarios)", ln=True)
    pdf.set_font("Arial", '', 10)
    for scenario, price in dcf_results.items():
        upside = ((price - c_price) / c_price) * 100 if c_price > 0 else 0
        pdf.cell(0, 6, f"{scenario}: {pdf_sym}{price:.2f} per share (Edge: {upside:+.1f}%)", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. Corporate Health & DuPont Breakdown", ln=True)
    pdf.set_font("Arial", '', 10)
    if dupont['valid']:
        pdf.cell(95, 6, f"Net Margin: {dupont['npm']:.2f}%")
        pdf.cell(95, 6, f"Asset Turnover: {dupont['ato']:.2f}x", ln=True)
        pdf.cell(95, 6, f"Equity Multiplier: {dupont['em']:.2f}x")
        pdf.cell(95, 6, f"ROE: {dupont['roe']:.2f}%", ln=True)
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 6, "Generated via Quantitative Asset Terminal. Not financial advice.", align='C')
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. SIDEBAR: MACRO CONTROL DECK
# ==========================================
st.sidebar.title("🎛️ Engine Config")
st.sidebar.markdown("Modify core institutional variables below.")

with st.sidebar.expander("🌍 Macro & Horizon Inputs", expanded=True):
    time_horizon = st.selectbox("Analysis Time Horizon:", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3)
    benchmark_input = st.text_input("Macro Benchmark Overlay:", "^GSPC", help="Used to map relative momentum.")
    global_rf = st.number_input("US Risk-Free Rate (%)", value=4.5, step=0.1) / 100
    global_erp = st.number_input("Equity Risk Premium (%)", value=5.5, step=0.1) / 100

with st.sidebar.expander("⚖️ Portfolio Targets", expanded=True):
    portfolio_capital = st.number_input("Initial Fund Capital", min_value=1000, value=1000000, step=10000)
    peer_input = st.text_input("Peer Tickers (Comma Separated):", "Mahindra, Reliance, Infosys")

# ==========================================
# 4. MAIN BODY: THE COMMAND LINE
# ==========================================
st.title("💼 Titan Institutional Research Terminal")

st.markdown('<div class="command-bar">', unsafe_allow_html=True)
cmd_col1, cmd_col2, cmd_col3 = st.columns([3, 1, 1])
with cmd_col1:
    raw_input = st.text_input("🔍 Command Line Search:", placeholder="Enter Keyword or Ticker (e.g., Tata, AAPL, TCS.NS)...", label_visibility="collapsed")
with cmd_col2:
    st.write("") 
    search_button = st.button("🚀 Execute Terminal", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

selected_ticker = None
if raw_input:
    candidates = get_search_candidates(raw_input)
    if candidates:
        options_dict = {c["display"]: c["symbol"] for c in candidates}
        with cmd_col3:
            st.write("") 
            selection = st.selectbox("Verify Asset:", list(options_dict.keys()), label_visibility="collapsed")
            selected_ticker = options_dict[selection]
    else:
        st.warning("No public market matches found.")

if "app_running" not in st.session_state: st.session_state.app_running = False
if search_button and selected_ticker: st.session_state.app_running = True

# ==========================================
# 5. EXECUTION MATRIX & MODULES
# ==========================================
if st.session_state.app_running and selected_ticker:
    st.divider()
    with st.spinner(f"Connecting to Exchange and running Quantitative Engines for {selected_ticker}..."):
        is_success, df_market = fetch_market_data(selected_ticker, time_horizon)
    
    if is_success and df_market is not None:
        try:
            raw_ticker = yf.Ticker(selected_ticker)
            info = get_ticker_info(selected_ticker)
            full_name = info.get('longName', info.get('shortName', selected_ticker))
            currency, curr_sym = info.get('currency', 'USD'), "₹" if info.get('currency') == "INR" else "$"
            deep_metrics = extract_financial_statements(raw_ticker, info)
        except:
            info, full_name, currency, curr_sym = {}, selected_ticker, "USD", "$"
            deep_metrics = {'revenue': None, 'net_income': None, 'total_assets': None, 'total_equity': None, 'fcf': None, 'total_liabilities': None, 'ebit': None, 'operating_cashflow': None, 'current_assets': None, 'current_liabilities': None}

        # TITAN UPGRADE: Sector Gate Classifications
        sector_str = str(info.get('sector', '')).lower()
        ind_str = str(info.get('industry', '')).lower()
        is_financial = 'bank' in ind_str or 'financial' in sector_str or 'insurance' in ind_str
        is_manufacturing = 'manufacturing' in sector_str or 'automotive' in ind_str or 'industrial' in sector_str
        is_indian = selected_ticker.endswith('.NS') or selected_ticker.endswith('.BO')

        current_price = df_market['close_price'].iloc[-1] if not df_market.empty else info.get('currentPrice', 1.0)
        beta_raw = info.get('beta', 1.0)
        
        raw_rev = float(deep_metrics.get('revenue', 1000000000.0) or 1000000000.0)
        raw_fcf = deep_metrics.get('fcf')
        fcf_base = float(raw_fcf) / 1000000.0 if raw_fcf is not None else (raw_rev * 0.12) / 1000000.0
        shares = float(info.get('sharesOutstanding', 100000000.0) or 100000000.0) / 1000000.0
        
        eps, bvps = info.get('trailingEps', 0), info.get('bookValue', 0)
        graham_number = np.sqrt(22.5 * eps * bvps) if eps > 0 and bvps > 0 else 0.0
        dividend_yield = info.get('dividendYield', 0)
        dividend_rate = info.get('dividendRate', 0)
        
        current_rf = 0.068 if is_indian else global_rf
        cost_of_equity = current_rf + (beta_raw * global_erp)
        total_debt = info.get('totalDebt', 0)
        market_cap = info.get('marketCap', 0)
        tax_rate_proxy = 0.25 
        
        if total_debt and market_cap and total_debt > 0:
            total_capital = total_debt + market_cap
            weight_equity = market_cap / total_capital
            weight_debt = total_debt / total_capital
            cost_of_debt = current_rf + 0.02 
            calculated_wacc = (weight_equity * cost_of_equity) + (weight_debt * cost_of_debt * (1 - tax_rate_proxy))
        else:
            calculated_wacc = cost_of_equity
        
        # Pre-generate PDF DCF/DDM dict to prevent Tear Sheet crash
        pdf_dcf = {}
        if is_financial:
            if dividend_rate and dividend_rate > 0:
                ke_bank = current_rf + (beta_raw * global_erp)
                g_bank = 0.04
                if ke_bank > g_bank:
                    pdf_dcf["DDM Target"] = (dividend_rate * (1 + g_bank)) / (ke_bank - g_bank)
        else:
            safe_fcf = fcf_base if fcf_base > 0 else (raw_rev * 0.10) / 1000000.0
            for n, g in {"Bear Case": 0.04, "Base Case": 0.08, "Bull Case": 0.14}.items():
                cfs = [safe_fcf * ((1 + g) ** y) for y in range(1, 6)]
                pv = sum([cfs[t] / ((1 + calculated_wacc) ** (t + 1)) for t in range(5)])
                pdf_dcf[n] = (pv + (((cfs[-1] * (1 + 0.04)) / (calculated_wacc - 0.04)) / ((1 + calculated_wacc) ** 5))) / shares

        ni, ta, te, rev = deep_metrics['net_income'], deep_metrics['total_assets'], deep_metrics['total_equity'], deep_metrics['revenue']
        dupont_data = {'valid': False}
        if ni and ta and te and rev and ta > 0 and te > 0 and rev > 0:
            dupont_data = {'valid': True, 'npm': (ni/rev)*100, 'ato': rev/ta, 'em': ta/te, 'roe': (ni/rev)*(rev/ta)*(ta/te)*100}

        col_head1, col_head2 = st.columns([3, 1])
        with col_head1:
            st.header(f"📊 {full_name} ({selected_ticker})")
            st.markdown(f"**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')} | **Exchange:** {info.get('exchange', 'N/A')}")
        with col_head2:
            st.write("") 
            pdf_bytes = generate_pdf_report(selected_ticker, full_name, info.get('sector', 'N/A'), curr_sym, current_price, info, pdf_dcf, dupont_data, graham_number)
            st.download_button("📥 PDF Tear Sheet", data=pdf_bytes, file_name=f"{selected_ticker}_Tear_Sheet.pdf", mime="application/pdf", use_container_width=True)
            csv_data = df_market.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Raw SQL Data (CSV)", data=csv_data, file_name=f"{selected_ticker}_historical.csv", mime='text/csv', use_container_width=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        tabs = st.tabs([
            "📈 Market", "📊 Comps", "💎 Value", "🔮 Valuation", "🏛️ Health", "⚖️ Portfolio", 
            "🤖 Forecast", "🧮 Options", "📊 Algo", "📅 Season", "🛡️ VaR", "🎭 Arb", 
            "🕵️ Insiders", "🌐 Macro"
        ])
        tab_market, tab_comps, tab_value, tab_dcf, tab_health, tab_mpt, tab_ml, tab_bs, tab_tech, tab_season, tab_risk, tab_arb, tab_insider, tab_macro = tabs
        
        with tab_market:
            if not df_market.empty:
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("Latest Close Price", f"{curr_sym}{current_price:.2f}")
                m_col2.metric("Trading Volume", f"{df_market['volume'].iloc[-1]:,}")
                m_col3.metric("Total Market Cap", f"{curr_sym}{info.get('marketCap', 0) / 1000000000:.2f} B" if info.get('marketCap') else "N/A")
                m_col4.metric("Systematic Risk (Beta)", f"{info.get('beta', 1.0):.2f}")
                
                sm_col1, sm_col2, sm_col3, sm_col4 = st.columns(4)
                short_ratio = info.get('shortRatio', 'N/A')
                sm_col1.metric("Short Ratio (Days to Cover)", short_ratio)
                high_52, low_52 = info.get('fiftyTwoWeekHigh'), info.get('fiftyTwoWeekLow')
                if high_52 and low_52 and current_price:
                    dist_to_high = ((current_price - high_52) / high_52) * 100
                    dist_to_low = ((current_price - low_52) / low_52) * 100
                else: dist_to_high, dist_to_low = 0, 0
                sm_col2.metric("52-Week High", f"{curr_sym}{high_52}" if high_52 else "N/A", f"{dist_to_high:.1f}%")
                sm_col3.metric("52-Week Low", f"{curr_sym}{low_52}" if low_52 else "N/A", f"{dist_to_low:.1f}%")
                sm_col4.metric("Institutional Ownership", f"{info.get('heldPercentInstitutions', 0) * 100:.2f}%" if info.get('heldPercentInstitutions') else "N/A")
                
                st.markdown(f"#### Raw Price Action & Moving Averages ({selected_ticker})")
                fig_raw = px.line(df_market, x='date', y=['close_price', 'sma_50', 'sma_200'], color_discrete_sequence=['#3b82f6', '#ef4444', '#10b981'])
                fig_raw.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Date", yaxis_title=f"Price ({currency})", legend_title_text="Metrics")
                st.plotly_chart(fig_raw, use_container_width=True)

                st.markdown(f"#### Relative Macro Performance: {selected_ticker} vs {benchmark_input}")
                benchmark_df = pd.DataFrame()
                if benchmark_input:
                    try:
                        b_data = fetch_peer_history([benchmark_input], time_horizon)
                        if not b_data.empty:
                            benchmark_df = pd.DataFrame(b_data).dropna().reset_index()
                            benchmark_df.columns = ['date', 'benchmark_close']
                            benchmark_df['date'] = pd.to_datetime(benchmark_df['date']).dt.tz_localize(None)
                    except: pass

                fig_price = go.Figure()
                start_price = df_market['close_price'].iloc[0]
                fig_price.add_trace(go.Scatter(x=df_market['date'], y=(df_market['close_price']/start_price)*100, name=selected_ticker, line=dict(color='#3b82f6', width=2)))
                if not benchmark_df.empty:
                    merged_df = pd.merge(df_market[['date']], benchmark_df, on='date', how='inner')
                    if not merged_df.empty:
                        start_bench = merged_df['benchmark_close'].iloc[0]
                        fig_price.add_trace(go.Scatter(x=merged_df['date'], y=(merged_df['benchmark_close']/start_bench)*100, name=f"Benchmark ({benchmark_input})", line=dict(color='#94a3b8', dash='dash')))
                fig_price.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Date", yaxis_title="Normalized Return %")
                st.plotly_chart(fig_price, use_container_width=True)

        with tab_comps:
            st.subheader("Relative Valuation Matrix")
            resolved_peers = []
            with st.spinner("Resolving peer identities..."):
                for raw_p in [p.strip() for p in peer_input.split(",") if p.strip()]:
                    p_cands = get_search_candidates(raw_p)
                    if p_cands and p_cands[0]['symbol'] not in resolved_peers and p_cands[0]['symbol'] != selected_ticker:
                        resolved_peers.append(p_cands[0]['symbol'])
            all_tickers_to_compare = [selected_ticker] + resolved_peers
            
            comps_data = []
            for t in all_tickers_to_compare:
                try:
                    p_info = get_ticker_info(t)
                    comps_data.append({"Ticker": t, "Company Name": p_info.get('shortName', t), "P/E Ratio": p_info.get('trailingPE', None), "EV/EBITDA": p_info.get('enterpriseToEbitda', None), "Net Margin (%)": p_info.get('profitMargins', 0) * 100 if p_info.get('profitMargins') else None})
                except: pass
            
            if comps_data:
                df_comps = pd.DataFrame(comps_data)
                clean_scatter = df_comps.dropna(subset=['P/E Ratio', 'Net Margin (%)', 'EV/EBITDA']).copy()
                clean_scatter = clean_scatter[clean_scatter['EV/EBITDA'] > 0]
                
                if not clean_scatter.empty:
                    fig_scatter = px.scatter(clean_scatter, x="P/E Ratio", y="Net Margin (%)", text="Ticker", size="EV/EBITDA", color="Ticker", title="Peer Positioning Scatter (Bubble Size = EV/EBITDA)")
                    fig_scatter.update_traces(textposition='top center')
                    fig_scatter.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_scatter, use_container_width=True)
                st.dataframe(df_comps.style.highlight_max(axis=0, subset=['Net Margin (%)']).format({"P/E Ratio": "{:.2f}x", "EV/EBITDA": "{:.2f}x", "Net Margin (%)": "{:.2f}%"}), use_container_width=True)

        with tab_value:
            st.subheader("💎 Legendary Value Investing Screener")
            v_col1, v_col2 = st.columns([1, 2])
            v_col1.metric("Benjamin Graham Number", f"{curr_sym}{graham_number:.2f}")
            if graham_number > current_price: v_col2.success(f"✅ **Undervalued:** Trading below Graham's intrinsic defense value by {((graham_number-current_price)/current_price)*100:.1f}%")
            elif graham_number > 0: v_col2.warning(f"⚠️ **Overvalued:** Trading above Graham's intrinsic defense value by {((current_price-graham_number)/graham_number)*100:.1f}%")
            else: v_col2.error("❌ Invalid data for Graham calculation (Negative EPS or BVPS detected).")
            
            st.markdown("#### Dividend Discount Model (Gordon Growth)")
            d_col1, d_col2 = st.columns(2)
            d_col1.metric("Current Dividend Yield", f"{dividend_yield*100:.2f}%" if dividend_yield else "N/A")
            if dividend_rate and dividend_rate > 0:
                assumed_div_growth = 0.03
                if calculated_wacc > assumed_div_growth:
                    gordon_value = (dividend_rate * (1 + assumed_div_growth)) / (calculated_wacc - assumed_div_growth)
                    d_col2.metric(f"DDM Fair Value (Assumes {assumed_div_growth*100}% Growth)", f"{curr_sym}{gordon_value:.2f}")
                else:
                    d_col2.warning("Cost of Capital is lower than assumed dividend growth; DDM invalid.")
            else:
                d_col2.info("Asset does not pay a valid dividend for DDM analysis.")

            ebit, ev = deep_metrics.get('ebit'), info.get('enterpriseValue')
            earnings_yield = (ebit / ev * 100) if ebit and ev and ev > 0 else 0
            st.metric("Acquirer's Multiple (Earnings Yield)", f"{earnings_yield:.2f}%", help="EBIT / Enterprise Value. Metric used by private equity to find cash-cow targets.")
            
            st.markdown("#### Piotroski F-Score (Proxy Metric)")
            f_score = 0
            if ni and ni > 0: f_score += 1
            if deep_metrics.get('operating_cashflow') and deep_metrics.get('operating_cashflow') > 0: f_score += 1
            if deep_metrics.get('operating_cashflow') and ni and deep_metrics.get('operating_cashflow') > ni: f_score += 1
            if info.get('returnOnAssets') and info.get('returnOnAssets') > 0: f_score += 1
            st.progress(f_score / 4)
            st.caption(f"Estimated Score: {f_score} / 4 (Based on available yfinance API fundamentals: Net Income, OCF, OCF > NI, ROA. Excludes leverage and margin trends due to API limits.)")

        with tab_dcf:
            st.subheader("Valuation Architecture Deck")
            if is_financial:
                st.warning("🏛️ WACC-based DCF is structurally invalid for Financial Institutions.")
                st.markdown("**Quantitative Rationale:** Banks treat debt as raw operational material rather than capital leverage. Free Cash Flow to Firm (FCFF) calculations are distorted by operational deposit inflows.")
                st.markdown("#### Structural Equity Valuation via DDM")
                if dividend_rate and dividend_rate > 0:
                    ke_bank = current_rf + (beta_raw * global_erp)
                    g_bank = 0.04
                    if ke_bank > g_bank:
                        ddm_val = (dividend_rate * (1 + g_bank)) / (ke_bank - g_bank)
                        st.metric("Implied Dividend Fair Value", f"{curr_sym}{ddm_val:.2f}")
                    else:
                        st.info("Cost of Equity is below baseline macro growth; DDM unstable.")
                else:
                    st.info("Asset does not distribute active dividends. Utilize Excess Returns framework offline.")
            else:
                st.markdown("#### Capital Asset Pricing Model & WACC")
                st.caption(f"**Cost of Equity (Ke):** Risk-Free Rate ({current_rf*100:.2f}%) + Beta ({beta_raw}) * ERP ({global_erp*100:.2f}%) = **{cost_of_equity*100:.2f}%**")
                if total_debt and total_debt > 0:
                    st.caption(f"**True WACC:** {calculated_wacc*100:.2f}% (Weighted Equity & Debt Structure)")
                else:
                    st.caption(f"**True WACC:** {calculated_wacc*100:.2f}% (No debt detected, WACC defaults to Ke)")
                
                dcf_col1, dcf_col2, dcf_col3 = st.columns(3)
                ui_fcf = dcf_col1.number_input("Base FCF Override (Millions)", value=float(fcf_base), step=10.0)
                
                if ui_fcf <= 0:
                    st.caption("⚠️ **Negative Base FCF Detected:** Normalizing baseline via operational revenue-proxy model to prevent compounding loss projections.")
                    ui_fcf = float(raw_rev * 0.10) / 1000000.0
                
                default_wacc_ui = min(max(float(calculated_wacc*100), 5.0), 30.0)
                ui_wacc = dcf_col2.slider("Discount Rate (WACC %)", 5.0, 30.0, default_wacc_ui, 0.5) / 100
                ui_t_growth = dcf_col3.slider("Terminal Growth Rate (%)", 1.0, 8.0, 4.0, 0.5) / 100
                
                ui_dcf_results = {}
                for n, g in {"Bear Case": 0.04, "Base Case": 0.08, "Bull Case": 0.14}.items():
                    cfs = [ui_fcf * ((1 + g) ** y) for y in range(1, 6)]
                    pv = sum([cfs[t] / ((1 + ui_wacc) ** (t + 1)) for t in range(5)])
                    tv = (cfs[-1] * (1 + ui_t_growth)) / (ui_wacc - ui_t_growth)
                    ui_dcf_results[n] = (pv + (tv / ((1 + ui_wacc) ** 5))) / shares

                st.plotly_chart(px.bar(pd.DataFrame(list(ui_dcf_results.items()), columns=["Scenario", "Target Price"]), x="Scenario", y="Target Price", text_auto=".2f", color="Scenario", color_discrete_map={"Bear Case": "#ef4444", "Base Case": "#3b82f6", "Bull Case": "#10b981"}), use_container_width=True)
                
                st.markdown("#### Reverse DCF (Market Implied Growth)")
                implied_g_range = np.linspace(-0.10, 0.30, 400)
                closest_diff = float('inf')
                implied_g_ans = 0
                for test_g in implied_g_range:
                    if ui_wacc > test_g:
                        cfs = [ui_fcf * ((1 + test_g) ** y) for y in range(1, 6)]
                        pv = sum([cfs[t] / ((1 + ui_wacc) ** (t + 1)) for t in range(5)])
                        tv = (cfs[-1] * (1 + test_g)) / (ui_wacc - test_g)
                        test_price = (pv + (tv / ((1 + ui_wacc) ** 5))) / shares
                        if abs(test_price - current_price) < closest_diff:
                            closest_diff = abs(test_price - current_price)
                            implied_g_ans = test_g
                st.metric("Market Implied Growth Rate", f"{implied_g_ans*100:.2f}%", help="If the company grows slower than this, the stock is currently overvalued.")
                
                st.markdown("#### WACC vs. Terminal Growth Sensitivity Matrix")
                wacc_range = np.arange(max(0.05, ui_wacc - 0.02), ui_wacc + 0.03, 0.01)
                tg_range = np.arange(max(0.01, ui_t_growth - 0.015), ui_t_growth + 0.02, 0.005)
                matrix = np.zeros((len(wacc_range), len(tg_range)))
                for i, w in enumerate(wacc_range):
                    for j, t in enumerate(tg_range):
                        cfs = [ui_fcf * ((1 + 0.08) ** y) for y in range(1, 6)]
                        pv = sum([cfs[year] / ((1 + w) ** (year + 1)) for year in range(5)])
                        tv = (cfs[-1] * (1 + t)) / (w - t) if w > t else 0
                        matrix[i, j] = (pv + (tv / ((1 + w) ** 5))) / shares
                fig_heat = px.imshow(matrix, labels=dict(x="Terminal Growth Rate", y="Discount Rate (WACC)", color="Implied Price"), x=[f"{x*100:.1f}%" for x in tg_range], y=[f"{y*100:.1f}%" for y in wacc_range], text_auto=".2f", color_continuous_scale="RdYlGn")
                st.plotly_chart(fig_heat, use_container_width=True)

        with tab_health:
            st.subheader("🏛️ Corporate Health & Forensics")
            
            st.markdown("#### Value Creation Engine (ROIC vs. Cost of Capital)")
            st.caption("Note: Invested Capital is approximated as (Total Assets - 0.4 * Total Liabilities) due to transient API limitations on specific operating liabilities.")
            tax_rate_proxy = 0.21
            if ebit and ta:
                nopat = ebit * (1 - tax_rate_proxy)
                invested_capital = ta - (deep_metrics.get('total_liabilities', 0) * 0.4) 
                roic = nopat / invested_capital if invested_capital > 0 else 0
                roic_wacc_spread = roic - calculated_wacc
                
                r_col1, r_col2 = st.columns([1, 2])
                r_col1.metric("Return on Invested Capital (ROIC)", f"{roic*100:.2f}%")
                if roic_wacc_spread > 0: r_col2.success(f"✅ **Value Creator:** ROIC exceeds WACC by {roic_wacc_spread*100:.2f}%.")
                else: r_col2.error(f"🚨 **Value Destroyer:** ROIC is below WACC by {abs(roic_wacc_spread)*100:.2f}%.")

            st.markdown("#### Altman Z-Score (Bankruptcy Probability Model)")
            if is_financial:
                st.info("Altman Z-Score analysis bypassed. Model metrics are incompatible with banking leverage profiles.")
            else:
                tl, mkt_cap = deep_metrics.get('total_liabilities'), info.get('marketCap')
                ca = deep_metrics.get('current_assets')
                cl = deep_metrics.get('current_liabilities')
                working_capital = (ca - cl) if ca and cl else 0
                
                if ta and rev and tl and mkt_cap and ebit and ta > 0 and tl > 0:
                    x1 = working_capital / ta 
                    x2 = te / ta
                    x3 = ebit / ta
                    x4 = mkt_cap / tl
                    
                    if is_manufacturing:
                        x5 = rev / ta
                        z_score = (1.2 * x1) + (1.4 * x2) + (3.3 * x3) + (0.6 * x4) + (1.0 * x5)
                        model_type = "Classic Manufacturing Z-Score"
                        safe_limit, distress_limit = 3.0, 1.8
                    else:
                        z_score = (6.56 * x1) + (3.26 * x2) + (6.72 * x3) + (1.05 * x4)
                        model_type = "Emerging Service & Tech Z''-Score"
                        safe_limit, distress_limit = 2.6, 1.1

                    z_col1, z_col2 = st.columns([1, 2])
                    z_col1.metric(f"{model_type}", f"{z_score:.2f}")
                    if z_score >= safe_limit: 
                        z_col2.success("✅ **Safe Zone:** Structural insolvency risk is mathematically remote.")
                    elif distress_limit <= z_score < safe_limit: 
                        z_col2.warning("⚠️ **Grey Zone:** Structural friction detected. Monitor capitalization trends closely.")
                    else: 
                        z_col2.error("🚨 **Distress Zone:** High profile vulnerability. Restructuring indicators present.")
                else: st.info("Insufficient deep balance sheet data to calculate Altman Z-Score.")
            
            st.markdown("---")
            if dupont_data['valid']:
                dp1, dp2, dp3, dp4 = st.columns(4)
                dp1.metric("Net Profit Margin", f"{dupont_data['npm']:.2f}%")
                dp2.metric("Asset Turnover", f"{dupont_data['ato']:.2f}x")
                dp3.metric("Equity Multiplier", f"{dupont_data['em']:.2f}x")
                dp4.metric("Deconstructed ROE", f"{dupont_data['roe']:.2f}%")

        with tab_mpt:
            st.subheader("Modern Portfolio Theory (MPT) Optimization")
            if len(all_tickers_to_compare) >= 2:
                with st.spinner("Running SLSQP Constrained Optimization..."):
                    mpt_data = fetch_peer_history(all_tickers_to_compare, time_horizon)
                    if not mpt_data.empty and isinstance(mpt_data, pd.DataFrame):
                        
                        # TITAN UPGRADE: Forward Fill and Weekly Resample for Cross-Border Markets
                        mpt_data = mpt_data.ffill().bfill()
                        weekly_data = mpt_data.resample('W').last()
                        ret = weekly_data.pct_change().dropna()
                        
                        valid_tickers = list(ret.columns)
                        num_assets = len(valid_tickers)
                        
                        if num_assets >= 2 and len(ret) > 10:
                            st.markdown("#### Inter-Asset Correlation Matrix (Weekly Resampled)")
                            fig_corr = px.imshow(ret.corr(), text_auto=".2f", color_continuous_scale="Blues", aspect="auto")
                            st.plotly_chart(fig_corr, use_container_width=True)
                            
                            ann_ret = ret.mean().values * 52
                            cov_matrix = ret.cov().values * 52
                            
                            def portfolio_performance(weights, mean_returns, cov_mat):
                                returns = np.sum(mean_returns * weights)
                                std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_mat, weights)))
                                return returns, std_dev
                                
                            def negative_sharpe(weights, mean_returns, cov_mat, rf_rate):
                                p_ret, p_std = portfolio_performance(weights, mean_returns, cov_mat)
                                return -(p_ret - rf_rate) / p_std if p_std > 0 else 0
                                
                            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
                            bounds = tuple((0.0, 1.0) for _ in range(num_assets))
                            init_guess = [1.0 / num_assets] * num_assets
                            
                            opt_res = sco.minimize(negative_sharpe, init_guess, args=(ann_ret, cov_matrix, current_rf), method='SLSQP', bounds=bounds, constraints=constraints)
                            opt_weights = opt_res.x
                            opt_ret, opt_std = portfolio_performance(opt_weights, ann_ret, cov_matrix)
                            max_sharpe = (opt_ret - current_rf) / opt_std
                            
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Optimized Expected Return", f"{opt_ret * 100:.2f}%")
                            m2.metric("Optimized Annual Risk", f"{opt_std * 100:.2f}%")
                            m3.metric("Maximized Sharpe Ratio", f"{max_sharpe:.2f}")
                            
                            res = np.zeros((3, 2000))
                            for i in range(2000):
                                w = np.random.random(num_assets); w /= np.sum(w)
                                p_ret = np.sum(ann_ret * w); p_std = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
                                res[0,i], res[1,i] = p_ret, p_std
                                res[2,i] = (p_ret - current_rf) / p_std 
                                
                            st.markdown("#### Efficient Frontier (SLSQP Global Maximum)")
                            fig_mpt = px.scatter(x=res[1,:], y=res[0,:], color=res[2,:], labels={'x': 'Risk', 'y': 'Return', 'color': 'Sharpe'}, title="Efficient Frontier Simulation")
                            fig_mpt.add_trace(go.Scatter(x=[opt_std], y=[opt_ret], mode='markers', marker=dict(color='red', size=18, symbol='star'), name='SLSQP Optimal'))
                            fig_mpt.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig_mpt, use_container_width=True)
                            
                            st.markdown(f"#### SLSQP Optimal Capital Deployment (Assuming {curr_sym}{portfolio_capital:,.2f})")
                            alloc_data = []
                            for idx, ticker in enumerate(valid_tickers):
                                alloc_data.append({"Asset": ticker, "Weight": opt_weights[idx], "Capital": opt_weights[idx] * portfolio_capital})
                            
                            fig_pie = px.pie(pd.DataFrame(alloc_data), names="Asset", values="Weight", hole=0.4, title="Target Capital Allocation Weights")
                            fig_pie.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig_pie, use_container_width=True)
                            st.dataframe(pd.DataFrame(alloc_data).style.format({"Weight": "{:.2%}", "Capital": f"{curr_sym}"+"{:,.2f}"}), use_container_width=True)
                        else:
                            st.warning("Data mismatch: Cross-exchange market holidays wiped out overlapping historical data.")
                    else:
                        st.warning("Failed to fetch adequate peer history for optimization.")
            else: st.warning("Add Custom Peers to run Portfolio Optimization.")

        with tab_ml:
            st.subheader(f"🤖 Machine Learning Price Forecast ({selected_ticker})")
            if not df_market.empty:
                returns = df_market['close_price'].pct_change().dropna()
                mu, sigma = returns.mean(), returns.std()
                days_to_predict, simulations = 30, 100
                last_price = df_market['close_price'].iloc[-1]
                
                sim_df = np.zeros((days_to_predict, simulations))
                sim_df[0] = last_price
                for t in range(1, days_to_predict):
                    shock = np.random.normal(loc=0, scale=1, size=simulations)
                    sim_df[t] = sim_df[t-1] * np.exp((mu - (sigma**2) / 2) + sigma * shock)
                
                fig_ml = go.Figure()
                for i in range(simulations):
                    fig_ml.add_trace(go.Scatter(x=np.arange(days_to_predict), y=sim_df[:, i], mode='lines', line=dict(color='#3b82f6', width=1), opacity=0.1, showlegend=False))
                
                mean_path = sim_df.mean(axis=1)
                upper_bound = np.percentile(sim_df, 95, axis=1)
                lower_bound = np.percentile(sim_df, 5, axis=1)
                
                fig_ml.add_trace(go.Scatter(x=np.arange(days_to_predict), y=mean_path, mode='lines', line=dict(color='#ef4444', width=3), name="Expected Mean Path"))
                fig_ml.add_trace(go.Scatter(x=np.arange(days_to_predict), y=upper_bound, mode='lines', line=dict(color='#10b981', width=2, dash='dash'), name="95th Percentile Bounds"))
                fig_ml.add_trace(go.Scatter(x=np.arange(days_to_predict), y=lower_bound, mode='lines', line=dict(color='#ef4444', width=2, dash='dash'), showlegend=False))
                
                fig_ml.update_layout(title=f"30-Day ML Monte Carlo Forecast Envelope ({selected_ticker})", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Days into Future", yaxis_title=f"Projected Price ({currency})")
                st.plotly_chart(fig_ml, use_container_width=True)
            else: st.warning("Insufficient historical data to run ML simulations.")
            
        with tab_bs:
            st.subheader(f"Institutional Options Desk ({selected_ticker})")
            st.markdown("#### Live Volatility Skew & Put/Call Ratio (PCR)")
            try:
                expirations = raw_ticker.options
                if expirations:
                    chain = raw_ticker.option_chain(expirations[0])
                    live_calls, live_puts = chain.calls, chain.puts
                    
                    total_call_vol = live_calls['volume'].sum() if 'volume' in live_calls.columns else 1
                    total_put_vol = live_puts['volume'].sum() if 'volume' in live_puts.columns else 0
                    pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 0
                    
                    pcr_col1, pcr_col2 = st.columns(2)
                    pcr_col1.metric(f"Live Put/Call Ratio (Exp: {expirations[0]})", f"{pcr:.2f}")
                    if pcr > 1: pcr_col2.error("🚨 **Bearish Sentiment:** More Puts are being traded than Calls.")
                    elif pcr < 0.7: pcr_col2.success("✅ **Bullish Sentiment:** Heavy Call volume relative to Puts.")
                    else: pcr_col2.info("⚖️ **Neutral Sentiment:** Option volume flow is balanced.")
                    
                    fig_skew = px.scatter(live_calls, x='strike', y='impliedVolatility', size='openInterest', color='impliedVolatility', 
                                          title=f"Implied Volatility Smile for Nearest Expiry: {expirations[0]}", color_continuous_scale="Viridis")
                    fig_skew.add_vline(x=current_price, line_dash="dash", line_color="gray", annotation_text="Current Price")
                    fig_skew.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Strike Price", yaxis_title="Implied Volatility")
                    st.plotly_chart(fig_skew, use_container_width=True)
                else: st.info("No live options chains available for this ticker.")
            except: st.warning("Could not fetch live options data from exchange.")

            st.markdown("#### Theoretical Premium Modeler")
            bs_col1, bs_col2, bs_col3, bs_col4 = st.columns(4)
            K = bs_col1.number_input("Strike Price (K)", value=float(current_price * 1.05), step=1.0)
            T = bs_col2.slider("Time to Expiry (Years)", 0.01, 5.0, 1.0, 0.05)
            r = bs_col3.slider("Risk-Free Rate (%)", 1.0, 10.0, float(current_rf*100), 0.1) / 100
            sigma = bs_col4.slider("Implied Volatility (%)", 5.0, 150.0, 30.0, 1.0) / 100
            
            d1 = (np.log(current_price / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            call_price = current_price * si.norm.cdf(d1, 0.0, 1.0) - K * np.exp(-r * T) * si.norm.cdf(d2, 0.0, 1.0)
            put_price = K * np.exp(-r * T) * si.norm.cdf(-d2, 0.0, 1.0) - current_price * si.norm.cdf(-d1, 0.0, 1.0)
            
            call_delta = si.norm.cdf(d1, 0.0, 1.0)
            put_delta = call_delta - 1
            gamma = si.norm.pdf(d1, 0.0, 1.0) / (current_price * sigma * np.sqrt(T))
            vega = current_price * si.norm.pdf(d1, 0.0, 1.0) * np.sqrt(T) / 100
            call_theta = (-current_price * si.norm.pdf(d1, 0.0, 1.0) * sigma / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * si.norm.cdf(d2, 0.0, 1.0)) / 365
            prob_itm_call = si.norm.cdf(d2, 0.0, 1.0) * 100
            
            st.markdown("---")
            call_col, put_col, prob_col = st.columns(3)
            call_col.metric(label="Call Premium (Right to Buy)", value=f"{curr_sym}{call_price:.2f}")
            put_col.metric(label="Put Premium (Right to Sell)", value=f"{curr_sym}{put_price:.2f}")
            prob_col.metric(label="Probability of Call ITM", value=f"{prob_itm_call:.1f}%")
            
            st.markdown("#### The Greeks (Risk Matrix)")
            g_col1, g_col2, g_col3, g_col4 = st.columns(4)
            g_col1.metric("Delta (Call)", f"{call_delta:.3f}")
            g_col2.metric("Gamma", f"{gamma:.4f}")
            g_col3.metric("Theta (Daily Decay)", f"{curr_sym}{call_theta:.3f}")
            g_col4.metric("Vega", f"{curr_sym}{vega:.3f}")

            st.markdown("##### Pricing Sensitivity Curve (Option Value vs. Underlying Price)")
            sim_prices = np.linspace(current_price * 0.5, current_price * 1.5, 100)
            sim_d1 = (np.log(sim_prices / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            sim_d2 = sim_d1 - sigma * np.sqrt(T)
            sim_calls = sim_prices * si.norm.cdf(sim_d1, 0.0, 1.0) - K * np.exp(-r * T) * si.norm.cdf(sim_d2, 0.0, 1.0)
            sim_puts = K * np.exp(-r * T) * si.norm.cdf(-sim_d2, 0.0, 1.0) - sim_prices * si.norm.cdf(-sim_d1, 0.0, 1.0)
            
            fig_bs = px.line(pd.DataFrame({"Price": sim_prices, "Call": sim_calls, "Put": sim_puts}), x="Price", y=["Call", "Put"], title=f"Theoretical Option Premium vs. Asset Price ({selected_ticker})", color_discrete_sequence=['#10b981', '#ef4444'])
            fig_bs.add_vline(x=current_price, line_dash="dash", line_color="gray", annotation_text="Current Price")
            fig_bs.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Underlying Asset Price", yaxis_title="Option Premium")
            st.plotly_chart(fig_bs, use_container_width=True)

        with tab_tech:
            st.subheader(f"Quantitative Trading Desk: Microstructure & Algos ({selected_ticker})")
            if not df_market.empty:
                st.markdown("#### Volume Profile (VPVR) - Institutional Price Nodes")
                tech_df = df_market.copy().sort_values('date')
                fig_vp = px.histogram(tech_df, y='close_price', x='volume', orientation='h', nbins=30, color_discrete_sequence=['#94a3b8'], title=f"Volume Accumulation by Price Level ({selected_ticker})")
                fig_vp.add_hline(y=current_price, line_dash="solid", line_color="#3b82f6", annotation_text="Current Price")
                fig_vp.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_title=f"Price Level ({currency})", xaxis_title="Total Historical Volume Traded")
                st.plotly_chart(fig_vp, use_container_width=True)

                st.markdown("#### Momentum Oscillators")
                tech_col1, tech_col2, tech_col3 = st.columns(3)
                bb_window = tech_col1.slider("Bollinger Window", 10, 50, 20, 1)
                rsi_window = tech_col2.slider("RSI Lookback", 7, 30, 14, 1)
                macd_fast = tech_col3.slider("MACD Fast EMA", 5, 20, 12, 1)

                tech_df['BB_Middle'] = tech_df['close_price'].rolling(window=bb_window).mean()
                tech_df['BB_Std'] = tech_df['close_price'].rolling(window=bb_window).std()
                tech_df['BB_Upper'] = tech_df['BB_Middle'] + (2.0 * tech_df['BB_Std'])
                tech_df['BB_Lower'] = tech_df['BB_Middle'] - (2.0 * tech_df['BB_Std'])
                
                delta = tech_df['close_price'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=rsi_window).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_window).mean()
                rs = gain / (loss + 1e-10) 
                tech_df['RSI'] = 100 - (100 / (1 + rs))
                
                ema_fast = tech_df['close_price'].ewm(span=macd_fast, adjust=False).mean()
                ema_slow = tech_df['close_price'].ewm(span=26, adjust=False).mean()
                tech_df['MACD'] = ema_fast - ema_slow
                tech_df['Signal_Line'] = tech_df['MACD'].ewm(span=9, adjust=False).mean()
                tech_df['MACD_Histogram'] = tech_df['MACD'] - tech_df['Signal_Line']
                tech_df = tech_df.dropna()
                
                fig_bb = go.Figure()
                fig_bb.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['close_price'], name='Close Price', line=dict(color='#3b82f6', width=2)))
                fig_bb.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['BB_Upper'], name='Upper Band', line=dict(color='#ef4444', width=1, dash='dot')))
                fig_bb.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['BB_Lower'], name='Lower Band', line=dict(color='#10b981', width=1, dash='dot')))
                
                max_p, min_p = tech_df['close_price'].max(), tech_df['close_price'].min()
                diff = max_p - min_p
                levels = [max_p, max_p - diff*0.236, max_p - diff*0.382, max_p - diff*0.5, max_p - diff*0.618, min_p]
                colors = ['#94a3b8', '#a855f7', '#3b82f6', '#10b981', '#f59e0b', '#94a3b8']
                for lvl, col in zip(levels, colors):
                    fig_bb.add_hline(y=lvl, line_dash="dot", line_color=col, opacity=0.5)
                
                fig_bb.update_layout(title=f"Volatility Channels & Fibonacci Retracements ({selected_ticker})", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_bb, use_container_width=True)
                
                osc_col1, osc_col2 = st.columns(2)
                with osc_col1:
                    fig_rsi = px.line(tech_df, x='date', y='RSI', title=f"Relative Strength Index ({selected_ticker})")
                    fig_rsi.add_hline(y=70, line_dash="dash", line_color="#ef4444")
                    fig_rsi.add_hline(y=30, line_dash="dash", line_color="#10b981")
                    fig_rsi.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_rsi, use_container_width=True)
                with osc_col2:
                    fig_macd = go.Figure()
                    fig_macd.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['MACD'], name='MACD', line=dict(color='#3b82f6')))
                    fig_macd.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['Signal_Line'], name='Signal', line=dict(color='#ef4444')))
                    fig_macd.add_trace(go.Bar(x=tech_df['date'], y=tech_df['MACD_Histogram'], name='Histogram', marker_color='#94a3b8'))
                    fig_macd.update_layout(title=f"MACD Momentum Trend ({selected_ticker})", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_macd, use_container_width=True)

        with tab_season:
            st.subheader(f"📅 Quantitative Seasonality & Regime Tracking ({selected_ticker})")
            if not df_market.empty:
                season_df = df_market.copy()
                season_df['Daily_Ret'] = season_df['close_price'].pct_change()
                season_df['Month'] = season_df['date'].dt.month_name().str[:3]
                season_df['Year'] = season_df['date'].dt.year
                season_df = season_df.dropna()
                
                pivot_season = pd.pivot_table(season_df, values='Daily_Ret', index='Year', columns='Month', aggfunc=lambda x: (np.prod(1+x)-1)*100)
                months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                pivot_season = pivot_season.reindex(columns=[m for m in months_order if m in pivot_season.columns])
                
                fig_season = px.imshow(pivot_season, text_auto=".1f", color_continuous_scale="RdYlGn", title=f"Historical Monthly Return Heatmap (%)")
                fig_season.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_season, use_container_width=True)
                
                st.markdown("#### Average Monthly Performance Matrix")
                avg_monthly = pivot_season.mean().reset_index()
                avg_monthly.columns = ['Month', 'Average Return %']
                fig_bar_season = px.bar(avg_monthly, x='Month', y='Average Return %', title=f"Average Return by Month ({selected_ticker})", color='Average Return %', color_continuous_scale="RdYlGn")
                fig_bar_season.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_bar_season, use_container_width=True)

        with tab_risk:
            st.subheader(f"Institutional Risk Engine: Value at Risk (VaR) & Expected Shortfall ({selected_ticker})")
            if not df_market.empty:
                risk_df = df_market.copy().sort_values('date')
                risk_df['Daily Return'] = risk_df['close_price'].pct_change()
                risk_df = risk_df.dropna()
                
                var_95, var_99 = np.percentile(risk_df['Daily Return'], 5), np.percentile(risk_df['Daily Return'], 1)
                cvar_95 = risk_df[risk_df['Daily Return'] <= var_95]['Daily Return'].mean()
                
                risk_df['Cumulative Max'] = risk_df['close_price'].cummax()
                risk_df['Drawdown'] = (risk_df['close_price'] - risk_df['Cumulative Max']) / risk_df['Cumulative Max']
                max_drawdown = risk_df['Drawdown'].min()
                
                r_col1, r_col2, r_col3 = st.columns(3)
                r_col1.metric("VaR (95%) Threshold", f"{var_95 * 100:.2f}%")
                r_col2.metric("Conditional VaR (Expected Shortfall)", f"{cvar_95 * 100:.2f}%")
                r_col3.metric("Max Historical Drawdown", f"{max_drawdown * 100:.2f}%")
                
                fig_var = px.histogram(risk_df, x='Daily Return', nbins=50, title="Empirical Return Distribution", color_discrete_sequence=['#3b82f6'])
                fig_var.add_vline(x=var_95, line_dash="dash", line_color="#ef4444", annotation_text="95% VaR")
                fig_var.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_tickformat='.2%')
                st.plotly_chart(fig_var, use_container_width=True)
                
                fig_dd = px.area(risk_df, x='date', y='Drawdown', title="Underwater Curve (Drawdown Profile)", color_discrete_sequence=['#ef4444'])
                fig_dd.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_tickformat='.2%')
                st.plotly_chart(fig_dd, use_container_width=True)

        with tab_arb:
            st.subheader("🎭 Statistical Arbitrage (Pairs Trading Spread)")
            default_peer = resolve_automatic_peer(selected_ticker, info.get('sector', ''), info.get('industry', ''))
            arb_ui_col1, arb_ui_col2 = st.columns([1, 2])
            with arb_ui_col1:
                arb_pair = st.text_input("📊 Target Arbitrage Counter-Pair Ticker:", value=default_peer, help="Automatically mapped based on sector symmetry. Override manually as needed.")
            
            if arb_pair:
                with st.spinner(f"Pulling dynamic arbitrage spread analytics for {arb_pair}..."):
                    try:
                        arb_data = fetch_peer_history([arb_pair.strip()], time_horizon)
                        if not arb_data.empty:
                            arb_df = pd.DataFrame(arb_data).dropna().reset_index()
                            arb_df.columns = ['date', 'arb_close']
                            arb_df['date'] = pd.to_datetime(arb_df['date']).dt.tz_localize(None)
                            
                            pair_df = pd.merge(df_market[['date', 'close_price']], arb_df, on='date', how='inner')
                            if not pair_df.empty:
                                pair_df['Spread_Ratio'] = pair_df['close_price'] / pair_df['arb_close']
                                rolling_mean = pair_df['Spread_Ratio'].rolling(window=20).mean()
                                rolling_std = pair_df['Spread_Ratio'].rolling(window=20).std()
                                pair_df['Z_Score'] = (pair_df['Spread_Ratio'] - rolling_mean) / rolling_std
                                pair_df = pair_df.dropna()
                                
                                fig_arb = px.line(pair_df, x='date', y='Z_Score', title=f"Spread Z-Score: {selected_ticker} vs {arb_pair.strip()}", color_discrete_sequence=['#a855f7'])
                                fig_arb.add_hline(y=2.0, line_dash="dash", line_color="#ef4444", annotation_text="Sell Target / Buy Pair Spread Threshold")
                                fig_arb.add_hline(y=-2.0, line_dash="dash", line_color="#10b981", annotation_text="Buy Target / Sell Pair Spread Threshold")
                                fig_arb.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                                st.plotly_chart(fig_arb, use_container_width=True)
                        else:
                            st.warning("Selected pair returned empty historical dataframe.")
                    except Exception as e: 
                        st.error(f"Execution failed for specified pair asset: {str(e)}")

        with tab_insider:
            st.subheader("🕵️ Smart Money Tracker (Institutional & Insider Activity)")
            has_insider_data = False
            try:
                holders = raw_ticker.institutional_holders
                if holders is not None and not holders.empty:
                    st.markdown("#### Top Institutional Holders")
                    st.dataframe(holders, use_container_width=True)
                    has_insider_data = True
            except: pass
            
            try:
                insider = raw_ticker.insider_purchases
                if insider is not None and not insider.empty:
                    st.markdown("#### Recent Insider Transaction Summary")
                    st.dataframe(insider, use_container_width=True)
                    has_insider_data = True
            except: pass
            
            if not has_insider_data:
                st.markdown("<br>", unsafe_allow_html=True)
                st.info("⚠️ SEC/SEBI Filing Data Currently Unavailable via Open-Source Feeds.")
                st.markdown("> **Operational Note:** Public regulatory registries for this asset require dedicated market data connections. In institutional installations, swapping the exchange engine from open-source to corporate lines (e.g., Bloomberg B-Pipe) immediately populates this module.")

        with tab_macro:
            st.subheader("🌐 Global Macroeconomic Regime")
            with st.spinner("Fetching Treasury Yields and Volatility Index..."):
                try:
                    yield_data = fetch_macro_history(time_horizon)
                    if not yield_data.empty:
                        yield_data = yield_data.dropna()
                        yield_data['Yield_Spread'] = yield_data['^TNX'] - yield_data['^IRX']
                        
                        m_col1, m_col2 = st.columns(2)
                        with m_col1:
                            fig_spread = px.area(x=yield_data.index, y=yield_data['Yield_Spread'], title="10Y-3M Yield Curve Spread", color_discrete_sequence=['#a855f7'])
                            fig_spread.add_hline(y=0, line_dash="solid", line_color="#ef4444", annotation_text="Inversion Line")
                            fig_spread.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_title="Spread Basis Points")
                            st.plotly_chart(fig_spread, use_container_width=True)
                        with m_col2:
                            fig_vix = px.line(x=yield_data.index, y=yield_data['^VIX'], title="CBOE Volatility Index (VIX)", color_discrete_sequence=['#ef4444'])
                            fig_vix.add_hline(y=20, line_dash="dash", line_color="#94a3b8", annotation_text="High Fear Threshold")
                            fig_vix.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_title="VIX Level")
                            st.plotly_chart(fig_vix, use_container_width=True)
                except: st.warning("Macro data currently unavailable.")

    else:
        st.error("🚨 Market entity not found.")