import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yfinance as yf
import requests
from fpdf import FPDF
import scipy.stats as si
from database_core import Base, Company, MarketData

# ==========================================
# 1. PAGE CONFIGURATION & STYLING
# ==========================================
st.set_page_config(page_title="Junior Analyst Terminal", page_icon="💼", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    h1, h2, h3 {color: #e2e8f0;}
    .stMetric {background-color: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid #334155;}
    .stTabs [data-baseweb="tab"] {font-size: 14px; font-weight: 600; color: #94a3b8;}
    .stTabs [data-baseweb="tab"][aria-selected="true"] {color: #3b82f6; border-bottom-color: #3b82f6;}
    </style>
""", unsafe_allow_html=True)

st.title("💼 Institutional Equity Research Terminal")
st.markdown("Enterprise Multi-Strategy Valuation & Financial Intelligence Workspace")
st.markdown("---")

# ==========================================
# 2. DATA PROCESSING & INGESTION ENGINE
# ==========================================
engine = create_engine('sqlite:///cqat_vault.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

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

def fetch_and_store_financials(ticker_symbol, time_horizon="1y"):
    session = Session()
    try:
        df = yf.download(ticker_symbol, period=time_horizon, progress=False)
        if df.empty:
            session.close()
            return False
        stock_info = yf.Ticker(ticker_symbol)
        
        # Only add to Company table if it doesn't exist
        if not session.query(Company).filter_by(ticker=ticker_symbol).first():
            new_company = Company(ticker=ticker_symbol, company_name=stock_info.info.get('shortName', ticker_symbol), sector=stock_info.info.get('sector', 'General'), industry=stock_info.info.get('industry', 'General'))
            session.add(new_company)
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['SMA_50'], df['SMA_200'] = df['Close'].rolling(window=50).mean(), df['Close'].rolling(window=200).mean()
        df = df.dropna()
        
        # Wipe old market data and save new timeframe
        session.query(MarketData).filter_by(ticker=ticker_symbol).delete()
        records = [MarketData(ticker=ticker_symbol, date=index.date(), close_price=float(row['Close']), volume=int(row['Volume']), sma_50=float(row['SMA_50']), sma_200=float(row['SMA_200'])) for index, row in df.iterrows()]
        session.bulk_save_objects(records)
        session.commit()
        session.close()
        return True
    except Exception:
        session.rollback()
        session.close()
        return False

def extract_financial_statements(raw_ticker, info):
    metrics = {'revenue': info.get('totalRevenue'), 'net_income': info.get('netIncomeToCommon'), 'total_assets': info.get('totalAssets'), 'total_equity': info.get('totalStockholderEquity'), 'fcf': info.get('freeCashflow')}
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
        if not cf.empty and metrics['fcf'] is None:
            if 'Free Cash Flow' in cf.index: metrics['fcf'] = cf.loc['Free Cash Flow'].iloc[0]
    except Exception: pass
    return metrics

def generate_pdf_report(ticker, full_name, sector, curr_sym, c_price, info, dcf_results, dupont):
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
    pdf.cell(95, 6, f"Price-to-Book (P/B): {info.get('priceToBook', 'N/A')}x", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Intrinsic Valuation (DCF 3-Scenario Analysis)", ln=True)
    pdf.set_font("Arial", '', 10)
    for scenario, price in dcf_results.items():
        upside = ((price - c_price) / c_price) * 100 if c_price > 0 else 0
        pdf.cell(0, 6, f"{scenario}: {pdf_sym}{price:.2f} per share (Edge: {upside:+.1f}%)", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. DuPont Operational Breakdown", ln=True)
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
# 3. INTERFACE COMMAND SIDEBAR
# ==========================================
st.sidebar.header("🔍 Asset Scanner")
raw_input = st.sidebar.text_input("Search Keyword or Brand:", "Tata")
selected_ticker = None
if raw_input:
    candidates = get_search_candidates(raw_input)
    if candidates:
        options_dict = {c["display"]: c["symbol"] for c in candidates}
        selection = st.sidebar.selectbox("Select Exact Market Asset:", list(options_dict.keys()))
        selected_ticker = options_dict[selection]
    else:
        st.sidebar.warning("No public market matches found.")

search_button = st.sidebar.button("Execute Terminal Boot Sequence")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Global Terminal Settings")
time_horizon = st.sidebar.selectbox("Analysis Time Horizon:", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3)
benchmark_input = st.sidebar.text_input("Macro Benchmark Overlay (Ticker):", "^GSPC", help="^GSPC is S&P 500, ^IXIC is NASDAQ, ^BSESN is BSE Sensex")

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Custom Peer Comps")
peer_input = st.sidebar.text_input("Peer Tickers / Names:", "Mahindra, Reliance, Infosys")

if "app_running" not in st.session_state: st.session_state.app_running = False
if search_button: st.session_state.app_running = True

# ==========================================
# 4. EXECUTION MATRIX
# ==========================================
if st.session_state.app_running and selected_ticker:
    with st.spinner(f"Intercepting live data for {selected_ticker} over {time_horizon}..."):
        is_success = fetch_and_store_financials(selected_ticker, time_horizon)
    
    if is_success:
        df_market = pd.read_sql(f"SELECT * FROM fact_market WHERE ticker = '{selected_ticker}' ORDER BY date ASC", engine)
        df_market['date'] = pd.to_datetime(df_market['date'])
        
        try:
            raw_ticker = yf.Ticker(selected_ticker)
            info = raw_ticker.info
            full_name = info.get('longName', info.get('shortName', selected_ticker))
            currency, curr_sym = info.get('currency', 'USD'), "₹" if info.get('currency') == "INR" else "$"
            deep_metrics = extract_financial_statements(raw_ticker, info)
        except:
            info, full_name, currency, curr_sym = {}, selected_ticker, "USD", "$"
            deep_metrics = {'revenue': None, 'net_income': None, 'total_assets': None, 'total_equity': None, 'fcf': None}

        current_price = df_market['close_price'].iloc[-1] if not df_market.empty else info.get('currentPrice', 1.0)
        
        # 1. Bulletproof Revenue Fallback
        raw_rev = deep_metrics.get('revenue')
        raw_rev = raw_rev if raw_rev is not None else 1000000000
        
        # 2. Bulletproof Free Cash Flow Fallback
        raw_fcf = deep_metrics.get('fcf')
        fcf_base = float(raw_fcf / 1000000) if raw_fcf is not None else (raw_rev * 0.12) / 1000000
        
        # 3. Bulletproof Shares Outstanding Fallback
        shares_raw = info.get('sharesOutstanding')
        shares = float(shares_raw / 1000000) if shares_raw is not None else 100.0
        
        pdf_dcf = {}
        for n, g in {"Bear Case": 0.04, "Base Case": 0.08, "Bull Case": 0.14}.items():
            cfs = [fcf_base * ((1 + g) ** y) for y in range(1, 6)]
            pv = sum([cfs[t] / ((1 + 0.10) ** (t + 1)) for t in range(5)])
            pdf_dcf[n] = (pv + (((cfs[-1] * (1 + 0.04)) / (0.10 - 0.04)) / ((1 + 0.10) ** 5))) / shares

        ni, ta, te, rev = deep_metrics['net_income'], deep_metrics['total_assets'], deep_metrics['total_equity'], deep_metrics['revenue']
        dupont_data = {'valid': False}
        if ni and ta and te and rev and ta > 0 and te > 0 and rev > 0:
            dupont_data = {'valid': True, 'npm': (ni/rev)*100, 'ato': rev/ta, 'em': ta/te, 'roe': (ni/rev)*(rev/ta)*(ta/te)*100}

        col_head, col_btn = st.columns([4, 1])
        with col_head:
            st.header(f"{full_name} ({selected_ticker})")
            st.markdown(f"**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')} | **Exchange:** {info.get('exchange', 'N/A')}")
        with col_btn:
            pdf_bytes = generate_pdf_report(selected_ticker, full_name, info.get('sector', 'N/A'), curr_sym, current_price, info, pdf_dcf, dupont_data)
            st.download_button("📥 Export PDF Tear Sheet", data=pdf_bytes, file_name=f"{selected_ticker}_Tear_Sheet.pdf", mime="application/pdf")
        
        tab_market, tab_comps, tab_dcf, tab_dupont, tab_mpt, tab_bs, tab_tech, tab_risk = st.tabs([
            "📈 Market & Macro", "📊 Comps Matrix", "🔮 DCF Heatmap", "🔍 DuPont", "⚖️ Quant Portfolio", "🧮 Black-Scholes", "📊 Algo Signals", "🛡️ VaR Risk"
        ])
        
        with tab_market:
            if not df_market.empty:
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("Latest Close Price", f"{curr_sym}{current_price:.2f}")
                m_col2.metric("Trading Volume", f"{df_market['volume'].iloc[-1]:,}")
                m_col3.metric("Total Market Cap", f"{curr_sym}{info.get('marketCap', 0) / 1000000000:.2f} B" if info.get('marketCap') else "N/A")
                m_col4.metric("Systematic Risk (Beta)", f"{info.get('beta', 1.0):.2f}")
                
                # Retrieve Benchmark Data
                benchmark_df = pd.DataFrame()
                if benchmark_input:
                    try:
                        b_data = yf.download(benchmark_input, period=time_horizon, progress=False)
                        if not b_data.empty:
                            if isinstance(b_data.columns, pd.MultiIndex): b_data.columns = b_data.columns.get_level_values(0)
                            benchmark_df = b_data[['Close']].dropna().reset_index()
                            benchmark_df.columns = ['date', 'benchmark_close']
                            benchmark_df['date'] = pd.to_datetime(benchmark_df['date']).dt.tz_localize(None)
                    except: pass

                fig_price = go.Figure()
                # Normalize values to 100 for direct percentage comparison
                start_price = df_market['close_price'].iloc[0]
                fig_price.add_trace(go.Scatter(x=df_market['date'], y=(df_market['close_price']/start_price)*100, name=selected_ticker, line=dict(color='#3b82f6', width=2)))
                
                if not benchmark_df.empty:
                    # Match dates and normalize benchmark
                    merged_df = pd.merge(df_market[['date']], benchmark_df, on='date', how='inner')
                    if not merged_df.empty:
                        start_bench = merged_df['benchmark_close'].iloc[0]
                        fig_price.add_trace(go.Scatter(x=merged_df['date'], y=(merged_df['benchmark_close']/start_bench)*100, name=f"Benchmark ({benchmark_input})", line=dict(color='#94a3b8', dash='dash')))

                fig_price.update_layout(title="Relative Macro Performance (Normalized to 100)", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Date", yaxis_title="Normalized Return %")
                st.plotly_chart(fig_price, width='stretch')
                
            st.subheader("Valuation Summary Multiples")
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            f_col1.metric("Trailing P/E Ratio", f"{info.get('trailingPE', 0):.2f}x" if info.get('trailingPE') else "N/A")
            f_col2.metric("EV / EBITDA", f"{info.get('enterpriseToEbitda', 0):.2f}x" if info.get('enterpriseToEbitda') else "N/A")
            f_col3.metric("Earnings Per Share (EPS)", f"{curr_sym}{info.get('trailingEps', 0):.2f}" if info.get('trailingEps') else "N/A")
            f_col4.metric("Price-to-Book (P/B)", f"{info.get('priceToBook', 0):.2f}x" if info.get('priceToBook') else "N/A")

        with tab_comps:
            st.subheader("Relative Valuation Matrix (Peer Comps)")
            resolved_peers = []
            with st.spinner("Resolving exact peer identities..."):
                for raw_p in [p.strip() for p in peer_input.split(",") if p.strip()]:
                    p_cands = get_search_candidates(raw_p)
                    if p_cands and p_cands[0]['symbol'] not in resolved_peers and p_cands[0]['symbol'] != selected_ticker:
                        resolved_peers.append(p_cands[0]['symbol'])
            
            all_tickers_to_compare = [selected_ticker] + resolved_peers
            st.caption(f"Active Peer Tracking Array: {', '.join(all_tickers_to_compare)}")
            
            comps_data = []
            for t in all_tickers_to_compare:
                try:
                    p_info = yf.Ticker(t).info
                    comps_data.append({
                        "Ticker": t, "Company Name": p_info.get('shortName', t), 
                        "P/E Ratio": p_info.get('trailingPE', None), 
                        "EV/EBITDA": p_info.get('enterpriseToEbitda', None), 
                        "Net Margin (%)": p_info.get('profitMargins', 0) * 100 if p_info.get('profitMargins') else None
                    })
                except: pass
            
            if comps_data:
                df_comps = pd.DataFrame(comps_data)
                
                # New Visual Scatter Plot
                st.markdown("#### Peer Positioning (P/E vs. Net Margin)")
                clean_scatter = df_comps.dropna(subset=['P/E Ratio', 'Net Margin (%)'])
                if not clean_scatter.empty:
                    fig_scatter = px.scatter(clean_scatter, x="P/E Ratio", y="Net Margin (%)", text="Ticker", size="EV/EBITDA", color="Ticker", title="Relative Value Mapping (Bubble Size = EV/EBITDA)")
                    fig_scatter.update_traces(textposition='top center')
                    fig_scatter.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_scatter, width='stretch')
                
                st.dataframe(df_comps.style.highlight_max(axis=0, subset=['Net Margin (%)']).format({"P/E Ratio": "{:.2f}x", "EV/EBITDA": "{:.2f}x", "Net Margin (%)": "{:.2f}%"}), use_container_width=True)

        with tab_dcf:
            st.subheader("Parametric 3-Scenario DCF & Sensitivity Heatmap")
            dcf_col1, dcf_col2, dcf_col3 = st.columns(3)
            ui_fcf = dcf_col1.number_input("Base FCF Override (Millions)", value=float(fcf_base), step=10.0)
            ui_wacc = dcf_col2.slider("Discount Rate (WACC %)", 5.0, 20.0, 10.0, 0.5) / 100
            ui_t_growth = dcf_col3.slider("Terminal Growth Rate (%)", 1.0, 8.0, 4.0, 0.5) / 100
            
            ui_dcf_results = {}
            for n, g in {"Bear Case": 0.04, "Base Case": 0.08, "Bull Case": 0.14}.items():
                cfs = [ui_fcf * ((1 + g) ** y) for y in range(1, 6)]
                pv = sum([cfs[t] / ((1 + ui_wacc) ** (t + 1)) for t in range(5)])
                tv = (cfs[-1] * (1 + ui_t_growth)) / (ui_wacc - ui_t_growth)
                ui_dcf_results[n] = (pv + (tv / ((1 + ui_wacc) ** 5))) / shares

            st.plotly_chart(px.bar(pd.DataFrame(list(ui_dcf_results.items()), columns=["Scenario", "Target Price"]), x="Scenario", y="Target Price", text_auto=".2f", color="Scenario", color_discrete_map={"Bear Case": "#ef4444", "Base Case": "#3b82f6", "Bull Case": "#10b981"}), width='stretch')
            
            # New Institutional Feature: Sensitivity Heatmap
            st.markdown("#### WACC vs. Terminal Growth Sensitivity Matrix")
            wacc_range = np.arange(max(0.05, ui_wacc - 0.02), ui_wacc + 0.03, 0.01)
            tg_range = np.arange(max(0.01, ui_t_growth - 0.015), ui_t_growth + 0.02, 0.005)
            
            matrix = np.zeros((len(wacc_range), len(tg_range)))
            for i, w in enumerate(wacc_range):
                for j, t in enumerate(tg_range):
                    cfs = [ui_fcf * ((1 + 0.08) ** y) for y in range(1, 6)] # Use Base Case Growth
                    pv = sum([cfs[year] / ((1 + w) ** (year + 1)) for year in range(5)])
                    tv = (cfs[-1] * (1 + t)) / (w - t) if w > t else 0
                    matrix[i, j] = (pv + (tv / ((1 + w) ** 5))) / shares
            
            fig_heat = px.imshow(matrix, labels=dict(x="Terminal Growth Rate", y="Discount Rate (WACC)", color="Implied Share Price"), x=[f"{x*100:.1f}%" for x in tg_range], y=[f"{y*100:.1f}%" for y in wacc_range], text_auto=".2f", color_continuous_scale="RdYlGn")
            st.plotly_chart(fig_heat, width='stretch')

        with tab_dupont:
            st.subheader("3-Stage DuPont Accounting Deconstruction")
            if dupont_data['valid']:
                dp1, dp2, dp3, dp4 = st.columns(4)
                dp1.metric("Net Profit Margin", f"{dupont_data['npm']:.2f}%")
                dp2.metric("Asset Turnover", f"{dupont_data['ato']:.2f}x")
                dp3.metric("Equity Multiplier", f"{dupont_data['em']:.2f}x")
                dp4.metric("Deconstructed ROE", f"{dupont_data['roe']:.2f}%")
                if dupont_data['em'] > 2.5: st.warning("⚠️ High Equity Multiplier implies heavy leverage.")
                else: st.success("✅ Corporate leverage is balanced.")
            else: st.warning("Accounting data missing for full DuPont breakdown.")

        with tab_mpt:
            st.subheader("Modern Portfolio Theory (MPT) Optimization")
            if len(all_tickers_to_compare) >= 2:
                with st.spinner(f"Running Monte Carlo simulation over {time_horizon}..."):
                    mpt_data = yf.download(all_tickers_to_compare, period=time_horizon, progress=False)['Close']
                    if not mpt_data.empty:
                        ret = mpt_data.pct_change().dropna()
                        
                        # New Institutional Feature: Asset Correlation Matrix
                        st.markdown("#### Inter-Asset Correlation Matrix")
                        corr_matrix = ret.corr()
                        fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale="Blues", aspect="auto")
                        st.plotly_chart(fig_corr, width='stretch')
                        
                        st.markdown("#### Monte Carlo Frontier Analysis")
                        ann_ret, cov = ret.mean() * 252, ret.cov() * 252
                        res, w_rec = np.zeros((3, 5000)), []
                        for i in range(5000):
                            w = np.random.random(len(all_tickers_to_compare)); w /= np.sum(w); w_rec.append(w)
                            p_ret = np.sum(ann_ret * w); p_std = np.sqrt(np.dot(w.T, np.dot(cov, w)))
                            res[0,i], res[1,i], res[2,i] = p_ret, p_std, (p_ret - 0.04) / p_std
                        m_idx = np.argmax(res[2])
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Expected Annual Return", f"{res[0, m_idx] * 100:.2f}%")
                        m2.metric("Expected Annual Risk", f"{res[1, m_idx] * 100:.2f}%")
                        m3.metric("Max Sharpe Ratio", f"{res[2, m_idx]:.2f}")
                        
                        fig_mpt = px.scatter(x=res[1,:], y=res[0,:], color=res[2,:], labels={'x': 'Risk', 'y': 'Return', 'color': 'Sharpe'}, title="Efficient Frontier")
                        fig_mpt.add_trace(go.Scatter(x=[res[1, m_idx]], y=[res[0, m_idx]], mode='markers', marker=dict(color='red', size=15, symbol='star'), name='Optimal'))
                        fig_mpt.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig_mpt, width='stretch')
                        st.plotly_chart(px.pie(pd.DataFrame({"Asset": all_tickers_to_compare, "Weighting": w_rec[m_idx]}), names="Asset", values="Weighting", hole=0.4, title="Optimal Capital Allocation"), width='stretch')
            else: st.warning("Add Custom Peers to run Portfolio Optimization.")
            
        with tab_bs:
            st.subheader("Black-Scholes Options Pricing Model")
            bs_col1, bs_col2, bs_col3, bs_col4 = st.columns(4)
            K = bs_col1.number_input("Strike Price (K)", value=float(current_price * 1.05), step=1.0)
            T = bs_col2.slider("Time to Expiry (Years)", 0.1, 5.0, 1.0, 0.1)
            r = bs_col3.slider("Risk-Free Rate (%)", 1.0, 10.0, 4.0, 0.1) / 100
            sigma = bs_col4.slider("Implied Volatility (%)", 5.0, 100.0, 25.0, 1.0) / 100
            
            d1 = (np.log(current_price / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            call_price = current_price * si.norm.cdf(d1, 0.0, 1.0) - K * np.exp(-r * T) * si.norm.cdf(d2, 0.0, 1.0)
            put_price = K * np.exp(-r * T) * si.norm.cdf(-d2, 0.0, 1.0) - current_price * si.norm.cdf(-d1, 0.0, 1.0)
            
            call_col, put_col = st.columns(2)
            call_col.metric(label="Call Option Value", value=f"{curr_sym}{call_price:.2f}")
            put_col.metric(label="Put Option Value", value=f"{curr_sym}{put_price:.2f}")
            
            sim_prices = np.linspace(current_price * 0.5, current_price * 1.5, 100)
            sim_d1 = (np.log(sim_prices / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            sim_d2 = sim_d1 - sigma * np.sqrt(T)
            sim_calls = sim_prices * si.norm.cdf(sim_d1, 0.0, 1.0) - K * np.exp(-r * T) * si.norm.cdf(sim_d2, 0.0, 1.0)
            sim_puts = K * np.exp(-r * T) * si.norm.cdf(-sim_d2, 0.0, 1.0) - sim_prices * si.norm.cdf(-sim_d1, 0.0, 1.0)
            
            fig_bs = px.line(pd.DataFrame({"Price": sim_prices, "Call": sim_calls, "Put": sim_puts}), x="Price", y=["Call", "Put"], title="Pricing Sensitivity Curve", color_discrete_sequence=['#10b981', '#ef4444'])
            fig_bs.add_vline(x=current_price, line_dash="dash", line_color="gray", annotation_text="Current Price")
            fig_bs.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_bs, width='stretch')

        with tab_tech:
            st.subheader("Quantitative Trading Desk: Algorithmic Overlays")
            if not df_market.empty:
                tech_col1, tech_col2, tech_col3 = st.columns(3)
                bb_window = tech_col1.slider("Bollinger Window", 10, 50, 20, 1)
                rsi_window = tech_col2.slider("RSI Lookback", 7, 30, 14, 1)
                macd_fast = tech_col3.slider("MACD Fast EMA", 5, 20, 12, 1)

                tech_df = df_market.copy().sort_values('date')
                
                # Bollinger
                tech_df['BB_Middle'] = tech_df['close_price'].rolling(window=bb_window).mean()
                tech_df['BB_Std'] = tech_df['close_price'].rolling(window=bb_window).std()
                tech_df['BB_Upper'] = tech_df['BB_Middle'] + (2.0 * tech_df['BB_Std'])
                tech_df['BB_Lower'] = tech_df['BB_Middle'] - (2.0 * tech_df['BB_Std'])
                
                # RSI
                delta = tech_df['close_price'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=rsi_window).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_window).mean()
                rs = gain / (loss + 1e-10) 
                tech_df['RSI'] = 100 - (100 / (1 + rs))
                
                # New Institutional Feature: MACD (Moving Average Convergence Divergence)
                ema_fast = tech_df['close_price'].ewm(span=macd_fast, adjust=False).mean()
                ema_slow = tech_df['close_price'].ewm(span=26, adjust=False).mean()
                tech_df['MACD'] = ema_fast - ema_slow
                tech_df['Signal_Line'] = tech_df['MACD'].ewm(span=9, adjust=False).mean()
                tech_df['MACD_Histogram'] = tech_df['MACD'] - tech_df['Signal_Line']
                
                tech_df = tech_df.dropna()
                
                # Plot BB
                fig_bb = go.Figure()
                fig_bb.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['close_price'], name='Close Price', line=dict(color='#3b82f6', width=2)))
                fig_bb.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['BB_Upper'], name='Upper Band', line=dict(color='#ef4444', width=1, dash='dot')))
                fig_bb.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['BB_Lower'], name='Lower Band', line=dict(color='#10b981', width=1, dash='dot')))
                fig_bb.update_layout(title="Volatility Channels (Bollinger Bands)", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_bb, width='stretch')
                
                # Plot RSI & MACD Side-by-Side
                osc_col1, osc_col2 = st.columns(2)
                with osc_col1:
                    fig_rsi = px.line(tech_df, x='date', y='RSI', title="Relative Strength Index (RSI)")
                    fig_rsi.add_hline(y=70, line_dash="dash", line_color="#ef4444")
                    fig_rsi.add_hline(y=30, line_dash="dash", line_color="#10b981")
                    fig_rsi.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_rsi, use_container_width=True)
                with osc_col2:
                    fig_macd = go.Figure()
                    fig_macd.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['MACD'], name='MACD', line=dict(color='#3b82f6')))
                    fig_macd.add_trace(go.Scatter(x=tech_df['date'], y=tech_df['Signal_Line'], name='Signal', line=dict(color='#ef4444')))
                    fig_macd.add_trace(go.Bar(x=tech_df['date'], y=tech_df['MACD_Histogram'], name='Histogram', marker_color='#94a3b8'))
                    fig_macd.update_layout(title="MACD Momentum Trend", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_macd, use_container_width=True)
            else:
                st.warning("Data unavailable.")
        
        with tab_risk:
            st.subheader("Institutional Risk Engine: Value at Risk (VaR) & Drawdown")
            if not df_market.empty:
                risk_df = df_market.copy().sort_values('date')
                risk_df['Daily Return'] = risk_df['close_price'].pct_change()
                risk_df = risk_df.dropna()
                
                var_95, var_99 = np.percentile(risk_df['Daily Return'], 5), np.percentile(risk_df['Daily Return'], 1)
                risk_df['Cumulative Max'] = risk_df['close_price'].cummax()
                risk_df['Drawdown'] = (risk_df['close_price'] - risk_df['Cumulative Max']) / risk_df['Cumulative Max']
                max_drawdown = risk_df['Drawdown'].min()
                
                r_col1, r_col2, r_col3 = st.columns(3)
                r_col1.metric("Historical VaR (95%)", f"{var_95 * 100:.2f}%")
                r_col2.metric("Historical VaR (99%)", f"{var_99 * 100:.2f}%")
                r_col3.metric("Max Historical Drawdown", f"{max_drawdown * 100:.2f}%")
                
                fig_var = px.histogram(risk_df, x='Daily Return', nbins=50, title="Empirical Return Distribution", color_discrete_sequence=['#3b82f6'])
                fig_var.add_vline(x=var_95, line_dash="dash", line_color="#ef4444", annotation_text="95% VaR")
                fig_var.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_tickformat='.2%')
                st.plotly_chart(fig_var, width='stretch')
                
                fig_dd = px.area(risk_df, x='date', y='Drawdown', title="Underwater Curve (Drawdown Profile)", color_discrete_sequence=['#ef4444'])
                fig_dd.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_tickformat='.2%')
                st.plotly_chart(fig_dd, width='stretch')
            else: st.warning("Insufficient data.")
    else:
        st.error("🚨 Market entity not found.")