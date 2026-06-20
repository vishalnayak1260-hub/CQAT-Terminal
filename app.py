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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    candidates = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        if 'quotes' in data:
            for quote in data['quotes']:
                if quote.get('quoteType') in ['EQUITY', 'ETF']:
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
            candidates.append({"display": f"Bombay Market Guess: {raw}.BO", "symbol": f"{raw}.BO"})
    return candidates

def fetch_and_store_financials(ticker_symbol):
    session = Session()
    exists = session.query(Company).filter_by(ticker=ticker_symbol).first()
    if exists:
        session.close()
        return True
    try:
        df = yf.download(ticker_symbol, period="1y", progress=False)
        if df.empty:
            session.close()
            return False
        stock_info = yf.Ticker(ticker_symbol)
        new_company = Company(ticker=ticker_symbol, company_name=stock_info.info.get('shortName', ticker_symbol), sector=stock_info.info.get('sector', 'General'), industry=stock_info.info.get('industry', 'General'))
        session.add(new_company)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['SMA_50'], df['SMA_200'] = df['Close'].rolling(window=50).mean(), df['Close'].rolling(window=200).mean()
        df = df.dropna()
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
    pdf.cell(95, 6, f"EV/EBITDA: {info.get('enterpriseToEbitda', 'N/A')}x", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Intrinsic Valuation (DCF 3-Scenario Analysis)", ln=True)
    pdf.set_font("Arial", '', 10)
    for scenario, price in dcf_results.items():
        upside = ((price - c_price) / c_price) * 100 if c_price > 0 else 0
        pdf.cell(0, 6, f"{scenario}: {pdf_sym}{price:.2f} per share (Implied Edge: {upside:+.1f}%)", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. DuPont Operational Breakdown", ln=True)
    pdf.set_font("Arial", '', 10)
    if dupont['valid']:
        pdf.cell(95, 6, f"Net Profit Margin: {dupont['npm']:.2f}%")
        pdf.cell(95, 6, f"Asset Turnover: {dupont['ato']:.2f}x", ln=True)
        pdf.cell(95, 6, f"Equity Multiplier (Leverage): {dupont['em']:.2f}x")
        pdf.cell(95, 6, f"Deconstructed ROE: {dupont['roe']:.2f}%", ln=True)
    else:
        pdf.cell(0, 6, "Insufficient fundamental data to generate DuPont breakdown.", ln=True)
        
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 6, "Generated automatically via the Quantitative Asset Terminal. Not financial advice.", align='C')
    
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. INTERFACE COMMAND SIDEBAR
# ==========================================
st.sidebar.header("Command Center")
raw_input = st.sidebar.text_input("1. Search Keyword or Brand:", "Tata")
selected_ticker = None
if raw_input:
    candidates = get_search_candidates(raw_input)
    if candidates:
        options_dict = {c["display"]: c["symbol"] for c in candidates}
        selection = st.sidebar.selectbox("2. Select Exact Market Asset:", list(options_dict.keys()))
        selected_ticker = options_dict[selection]
    else:
        st.sidebar.warning("No public market matches found.")

search_button = st.sidebar.button("3. Run Financial Intelligence Suite")
st.sidebar.markdown("---")
st.sidebar.subheader("📐 Custom Peer Comps")
peer_input = st.sidebar.text_input("Peer Tickers / Names:", "Mahindra, Reliance, Infosys")

# ==========================================
# 4. EXECUTION MATRIX
# ==========================================
if search_button and selected_ticker:
    with st.spinner(f"Intercepting live data for {selected_ticker}..."):
        is_success = fetch_and_store_financials(selected_ticker)
    
    if is_success:
        df_market = pd.read_sql(f"SELECT * FROM fact_market WHERE ticker = '{selected_ticker}'", engine)
        
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
        
        raw_rev, raw_fcf = deep_metrics.get('revenue', 1000000000), deep_metrics.get('fcf')
        fcf_base = float(raw_fcf / 1000000) if raw_fcf else (raw_rev * 0.12) / 1000000
        shares = float(info.get('sharesOutstanding', 100000000) / 1000000)
        wacc, t_growth = 0.10, 0.04
        scenarios = {"Bear Case": 0.04, "Base Case": 0.08, "Bull Case": 0.14}
        dcf_results = {}
        for n, g in scenarios.items():
            cfs = [fcf_base * ((1 + g) ** y) for y in range(1, 6)]
            pv = sum([cfs[t] / ((1 + wacc) ** (t + 1)) for t in range(5)])
            tv = (cfs[-1] * (1 + t_growth)) / (wacc - t_growth)
            dcf_results[n] = (pv + (tv / ((1 + wacc) ** 5))) / shares

        ni, ta, te, rev = deep_metrics['net_income'], deep_metrics['total_assets'], deep_metrics['total_equity'], deep_metrics['revenue']
        dupont_data = {'valid': False}
        if ni and ta and te and rev and ta > 0 and te > 0 and rev > 0:
            dupont_data = {'valid': True, 'npm': (ni/rev)*100, 'ato': rev/ta, 'em': ta/te, 'roe': (ni/rev)*(rev/ta)*(ta/te)*100}

        col_head, col_btn = st.columns([3, 1])
        with col_head:
            st.header(f"{full_name} ({selected_ticker})")
            st.markdown(f"**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')} | **Exchange:** {info.get('exchange', 'N/A')}")
        with col_btn:
            pdf_bytes = generate_pdf_report(selected_ticker, full_name, info.get('sector', 'N/A'), curr_sym, current_price, info, dcf_results, dupont_data)
            st.download_button(label="📥 Export PDF Tear Sheet", data=pdf_bytes, file_name=f"{selected_ticker}_Tear_Sheet.pdf", mime="application/pdf")
        
        tab_market, tab_comps, tab_dcf, tab_dupont, tab_mpt, tab_bs = st.tabs([
            "📈 Market Performance", "📊 Peer Benchmarking", "🔮 DCF Valuation", "🔍 DuPont Analysis", "⚖️ Quant Portfolio Optimizer", "🧮 Options (Black-Scholes)"
        ])
        
        with tab_market:
            if not df_market.empty:
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("Latest Close Price", f"{curr_sym}{current_price:.2f}")
                m_col2.metric("Trading Volume", f"{df_market['volume'].iloc[-1]:,}")
                m_col3.metric("Total Market Cap", f"{curr_sym}{info.get('marketCap', 0) / 1000000000:.2f} B" if info.get('marketCap') else "N/A")
                m_col4.metric("Systematic Risk (Beta)", f"{info.get('beta', 1.0):.2f}")
                
                fig_price = px.line(df_market, x='date', y=['close_price', 'sma_50', 'sma_200'], title="Price Action Vector vs Moving Average Support Levels", color_discrete_sequence=['#3b82f6', '#ef4444', '#10b981'])
                fig_price.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="Date", yaxis_title=f"Price ({currency})")
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
                    comps_data.append({"Ticker": t, "Company Name": p_info.get('shortName', t), "P/E Ratio": p_info.get('trailingPE', None), "EV/EBITDA": p_info.get('enterpriseToEbitda', None), "P/B Ratio": p_info.get('priceToBook', None), "Net Margin (%)": p_info.get('profitMargins', 0) * 100 if p_info.get('profitMargins') else None})
                except: pass
            if comps_data:
                st.dataframe(pd.DataFrame(comps_data).style.highlight_max(axis=0, subset=['Net Margin (%)']).format({"P/E Ratio": "{:.2f}x", "EV/EBITDA": "{:.2f}x", "P/B Ratio": "{:.2f}x", "Net Margin (%)": "{:.2f}%"}), use_container_width=True)

        with tab_dcf:
            st.subheader("Structured 3-Scenario Free Cash Flow Engine")
            st.markdown(f"**Baseline Parameter:** TTM Free Cash Flow captured at **{curr_sym}{fcf_base:,.2f} Million**.")
            st.plotly_chart(px.bar(pd.DataFrame(list(dcf_results.items()), columns=["Scenario", "Target Price"]), x="Scenario", y="Target Price", text_auto=".2f", color="Scenario", color_discrete_map={"Bear Case": "#ef4444", "Base Case": "#3b82f6", "Bull Case": "#10b981"}), width='stretch')
            st.markdown(f"**Current Market Trading Price:** {curr_sym}{current_price:.2f}")

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
                with st.spinner("Running Monte Carlo simulation..."):
                    mpt_data = yf.download(all_tickers_to_compare, period="2y", progress=False)['Close']
                    if not mpt_data.empty:
                        ret = mpt_data.pct_change().dropna()
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
            st.markdown("Calculates the theoretical fair-market value of European Call and Put options using advanced stochastic calculus.")
            
            # The Inputs
            st.markdown("#### Option Contract Parameters")
            bs_col1, bs_col2, bs_col3, bs_col4 = st.columns(4)
            # Default strike price is slightly "Out of the Money" (5% above current price)
            K = bs_col1.number_input("Strike Price (K)", value=float(current_price * 1.05), step=1.0)
            T = bs_col2.slider("Time to Expiry (Years)", 0.1, 5.0, 1.0, 0.1)
            r = bs_col3.slider("Risk-Free Rate (%)", 1.0, 10.0, 4.0, 0.1) / 100
            sigma = bs_col4.slider("Implied Volatility (%)", 5.0, 100.0, 25.0, 1.0) / 100
            
            # The Mathematics
            d1 = (np.log(current_price / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            
            call_price = current_price * si.norm.cdf(d1, 0.0, 1.0) - K * np.exp(-r * T) * si.norm.cdf(d2, 0.0, 1.0)
            put_price = K * np.exp(-r * T) * si.norm.cdf(-d2, 0.0, 1.0) - current_price * si.norm.cdf(-d1, 0.0, 1.0)
            
            st.markdown("---")
            st.markdown(f"#### Theoretical Premium Valuation for {selected_ticker}")
            call_col, put_col = st.columns(2)
            call_col.metric(label="Call Option Value (Right to Buy)", value=f"{curr_sym}{call_price:.2f}")
            put_col.metric(label="Put Option Value (Right to Sell)", value=f"{curr_sym}{put_price:.2f}")
            
            # Visualizing the Option Curve
            st.markdown("##### Pricing Sensitivity Curve (Option Value vs. Underlying Price)")
            sim_prices = np.linspace(current_price * 0.5, current_price * 1.5, 100)
            sim_d1 = (np.log(sim_prices / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            sim_d2 = sim_d1 - sigma * np.sqrt(T)
            sim_calls = sim_prices * si.norm.cdf(sim_d1, 0.0, 1.0) - K * np.exp(-r * T) * si.norm.cdf(sim_d2, 0.0, 1.0)
            sim_puts = K * np.exp(-r * T) * si.norm.cdf(-sim_d2, 0.0, 1.0) - sim_prices * si.norm.cdf(-sim_d1, 0.0, 1.0)
            
            bs_df = pd.DataFrame({"Underlying Asset Price": sim_prices, "Call Value": sim_calls, "Put Value": sim_puts})
            fig_bs = px.line(bs_df, x="Underlying Asset Price", y=["Call Value", "Put Value"], title="Theoretical Option Premium vs. Asset Price", color_discrete_sequence=['#10b981', '#ef4444'])
            fig_bs.add_vline(x=current_price, line_dash="dash", line_color="gray", annotation_text="Current Market Price")
            fig_bs.add_vline(x=K, line_dash="dash", line_color="white", annotation_text="Strike Price (K)")
            fig_bs.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_title="Option Premium Value")
            st.plotly_chart(fig_bs, width='stretch')
            
    else:
        st.error("🚨 Market entity not found or data retrieval failed.")