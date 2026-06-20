import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yfinance as yf
import requests
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
                    display_string = f"{name} ({symbol}) - {exch}"
                    candidates.append({"display": display_string, "symbol": symbol})
    except Exception:
        pass
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
        company_name = stock_info.info.get('shortName', ticker_symbol)
        sector = stock_info.info.get('sector', 'General')
        industry = stock_info.info.get('industry', 'General')
        new_company = Company(ticker=ticker_symbol, company_name=company_name, sector=sector, industry=industry)
        session.add(new_company)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df = df.dropna()
        session.query(MarketData).filter_by(ticker=ticker_symbol).delete()
        records = [
            MarketData(ticker=ticker_symbol, date=index.date(), close_price=float(row['Close']), 
                       volume=int(row['Volume']), sma_50=float(row['SMA_50']), sma_200=float(row['SMA_200']))
            for index, row in df.iterrows()
        ]
        session.bulk_save_objects(records)
        session.commit()
        session.close()
        return True
    except Exception:
        session.rollback()
        session.close()
        return False

def extract_financial_statements(raw_ticker, info):
    metrics = {
        'revenue': info.get('totalRevenue'), 'net_income': info.get('netIncomeToCommon'),
        'total_assets': info.get('totalAssets'), 'total_equity': info.get('totalStockholderEquity'),
        'fcf': info.get('freeCashflow')
    }
    try:
        inc = raw_ticker.financials
        bs = raw_ticker.balance_sheet
        cf = raw_ticker.cashflow
        if not inc.empty and metrics['revenue'] is None:
            for key in ['Total Revenue', 'Operating Revenue', 'Revenue']:
                if key in inc.index: metrics['revenue'] = inc.loc[key].iloc[0]; break
        if not inc.empty and metrics['net_income'] is None:
            for key in ['Net Income', 'Net Income Common Stockholders']:
                if key in inc.index: metrics['net_income'] = inc.loc[key].iloc[0]; break
        if not bs.empty and metrics['total_assets'] is None:
            if 'Total Assets' in bs.index: metrics['total_assets'] = bs.loc['Total Assets'].iloc[0]
        if not bs.empty and metrics['total_equity'] is None:
            for key in ['Stockholders Equity', 'Common Stock Equity']:
                if key in bs.index: metrics['total_equity'] = bs.loc[key].iloc[0]; break
        if not cf.empty and metrics['fcf'] is None:
            if 'Free Cash Flow' in cf.index: metrics['fcf'] = cf.loc['Free Cash Flow'].iloc[0]
    except Exception:
        pass
    return metrics

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
        st.sidebar.warning("No public market matches found for that keyword.")

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
            currency = info.get('currency', 'USD')
            curr_sym = "₹" if currency == "INR" else "$"
            deep_metrics = extract_financial_statements(raw_ticker, info)
        except:
            info = {}
            full_name = selected_ticker
            currency = "USD"
            curr_sym = "$"
            deep_metrics = {'revenue': None, 'net_income': None, 'total_assets': None, 'total_equity': None, 'fcf': None}

        st.header(f"{full_name} ({selected_ticker})")
        st.markdown(f"**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')} | **Exchange:** {info.get('exchange', 'N/A')}")
        
        tab_market, tab_comps, tab_dcf, tab_dupont, tab_mpt = st.tabs([
            "📈 Market Performance", 
            "📊 Peer Benchmarking", 
            "🔮 DCF Valuation",
            "🔍 DuPont Analysis",
            "⚖️ Quant Portfolio Optimizer"
        ])
        
        with tab_market:
            if not df_market.empty:
                current_price = df_market['close_price'].iloc[-1]
                volume = df_market['volume'].iloc[-1]
                raw_cap = info.get('marketCap', 0)
                market_cap_formatted = f"{curr_sym}{raw_cap / 1000000000:.2f} B" if raw_cap else "N/A"
                beta_val = info.get('beta', 1.0)
                
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("Latest Close Price", f"{curr_sym}{current_price:.2f}")
                m_col2.metric("Trading Volume", f"{volume:,}")
                m_col3.metric("Total Market Cap", market_cap_formatted)
                m_col4.metric("Systematic Risk (Beta)", f"{beta_val:.2f}")
                
                fig_price = px.line(df_market, x='date', y=['close_price', 'sma_50', 'sma_200'], 
                                    title="Price Action Vector vs Moving Average Support Levels",
                                    color_discrete_sequence=['#3b82f6', '#ef4444', '#10b981'])
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
            raw_peer_strings = [p.strip() for p in peer_input.split(",") if p.strip()]
            resolved_peers = []
            
            with st.spinner("Resolving exact peer identities..."):
                for raw_p in raw_peer_strings:
                    p_cands = get_search_candidates(raw_p)
                    if p_cands:
                        best_match = p_cands[0]['symbol']
                        if best_match not in resolved_peers and best_match != selected_ticker:
                            resolved_peers.append(best_match)
            
            all_tickers_to_compare = [selected_ticker] + resolved_peers
            st.caption(f"Active Peer Tracking Array: {', '.join(all_tickers_to_compare)}")
            
            comps_data = []
            with st.spinner("Extracting operational metrics across peer group..."):
                for t in all_tickers_to_compare:
                    try:
                        p_ticker = yf.Ticker(t)
                        p_info = p_ticker.info
                        comps_data.append({
                            "Ticker": t, "Company Name": p_info.get('shortName', t),
                            "P/E Ratio": p_info.get('trailingPE', None), "EV/EBITDA": p_info.get('enterpriseToEbitda', None),
                            "P/B Ratio": p_info.get('priceToBook', None), "Net Margin (%)": p_info.get('profitMargins', 0) * 100 if p_info.get('profitMargins') else None
                        })
                    except:
                        pass
            if comps_data:
                df_comps = pd.DataFrame(comps_data)
                st.dataframe(df_comps.style.highlight_max(axis=0, subset=['Net Margin (%)']).format({
                    "P/E Ratio": "{:.2f}x", "EV/EBITDA": "{:.2f}x", "P/B Ratio": "{:.2f}x", "Net Margin (%)": "{:.2f}%"
                }), use_container_width=True)

        with tab_dcf:
            st.subheader("Structured 3-Scenario Free Cash Flow Engine")
            raw_rev = deep_metrics.get('revenue')
            raw_rev = raw_rev if raw_rev else 1000000000
            raw_fcf = deep_metrics.get('fcf')
            fcf_base_millions = float(raw_fcf / 1000000) if raw_fcf else (raw_rev * 0.12) / 1000000
            
            st.markdown(f"**Baseline Parameter:** TTM Free Cash Flow captured at **{curr_sym}{fcf_base_millions:,.2f} Million**.")
            
            dcf_col1, dcf_col2, dcf_col3 = st.columns(3)
            wacc_input = dcf_col1.slider("Discount Rate (WACC %)", 6.0, 16.0, 10.0, step=0.5) / 100
            terminal_growth = dcf_col2.slider("Terminal Perpetuity Growth (% Growth)", 1.0, 6.0, 4.0, step=0.2) / 100
            shares_raw = info.get('sharesOutstanding', 50000000)
            shares_outstanding = dcf_col3.number_input("Shares Outstanding (Millions)", value=float(shares_raw / 1000000) if shares_raw else 100.0, min_value=1.0)
            
            scenarios = {"Bear Case (Conservative)": {"growth": 0.04, "color": "#ef4444"}, "Base Case (Market Consensus)": {"growth": 0.08, "color": "#3b82f6"}, "Bull Case (Aggressive Expansion)": {"growth": 0.14, "color": "#10b981"}}
            dcf_results = {}
            for name, config in scenarios.items():
                g = config["growth"]
                projected_cfs = [fcf_base_millions * ((1 + g) ** year) for year in range(1, 6)]
                pv_cfs = [projected_cfs[t] / ((1 + wacc_input) ** (t + 1)) for t in range(5)]
                terminal_value = (projected_cfs[-1] * (1 + terminal_growth)) / (wacc_input - terminal_growth)
                pv_terminal_value = terminal_value / ((1 + wacc_input) ** 5)
                total_intrinsic_value = sum(pv_cfs) + pv_terminal_value
                dcf_results[name] = total_intrinsic_value / shares_outstanding
            
            fig_dcf = px.bar(pd.DataFrame(list(dcf_results.items()), columns=["Scenario", "Target Price Per Share"]), x="Scenario", y="Target Price Per Share", text_auto=".2f", color="Scenario", color_discrete_map={k: v["color"] for k, v in scenarios.items()})
            st.plotly_chart(fig_dcf, width='stretch')
            
            c_price = df_market['close_price'].iloc[-1] if not df_market.empty else info.get('currentPrice', info.get('previousClose', 1.0))
            st.markdown(f"**Current Market Trading Price:** {curr_sym}{c_price:.2f}")
            
            dcf_metrics_cols = st.columns(3)
            idx = 0
            for name, val in dcf_results.items():
                upside = ((val - c_price) / c_price) * 100 if c_price > 0 else 0
                dcf_metrics_cols[idx].metric(name, f"{curr_sym}{val:.2f}", f"{upside:+.1f}% Implied Edge")
                idx += 1

        with tab_dupont:
            st.subheader("3-Stage DuPont Accounting Deconstruction")
            net_income, total_assets, total_equity, revenue = deep_metrics.get('net_income'), deep_metrics.get('total_assets'), deep_metrics.get('total_equity'), deep_metrics.get('revenue')
            
            if net_income and total_assets and total_equity and revenue and total_assets > 0 and total_equity > 0 and revenue > 0:
                net_profit_margin, asset_turnover, equity_multiplier = net_income / revenue, revenue / total_assets, total_assets / total_equity
                calculated_roe = net_profit_margin * asset_turnover * equity_multiplier
                
                dp_col1, dp_col2, dp_col3, dp_col4 = st.columns(4)
                dp_col1.metric("Net Profit Margin", f"{net_profit_margin * 100:.2f}%")
                dp_col2.metric("Asset Turnover", f"{asset_turnover:.2f}x")
                dp_col3.metric("Equity Multiplier", f"{equity_multiplier:.2f}x")
                dp_col4.metric("Deconstructed ROE", f"{calculated_roe * 100:.2f}%")
                
                if equity_multiplier > 2.5: st.warning("⚠️ Risk Warning: High Equity Multiplier implies heavy leverage.")
                else: st.success("✅ Operational Health: Corporate leverage is balanced.")
            else:
                st.warning("Accounting data for a full DuPont breakdown is missing for this ticker.")
                
        with tab_mpt:
            st.subheader("Modern Portfolio Theory (MPT) Optimization")
            st.markdown("Uses a Monte Carlo simulation (5,000 iterations) across the target asset and peer group to find the Mathematically Optimal Portfolio Weighting (Maximum Sharpe Ratio).")
            
            if len(all_tickers_to_compare) >= 2:
                with st.spinner("Downloading historical arrays and running Monte Carlo simulation..."):
                    # 1. Download 2 years of data for all tickers
                    mpt_data = yf.download(all_tickers_to_compare, period="2y", progress=False)['Close']
                    
                    if not mpt_data.empty:
                        # 2. Calculate Daily Returns and Annualize
                        daily_returns = mpt_data.pct_change().dropna()
                        annual_returns = daily_returns.mean() * 252
                        cov_matrix = daily_returns.cov() * 252
                        
                        num_portfolios = 5000
                        results = np.zeros((3, num_portfolios))
                        weights_record = []
                        
                        # 3. Simulate 5,000 random weight combinations
                        for i in range(num_portfolios):
                            weights = np.random.random(len(all_tickers_to_compare))
                            weights /= np.sum(weights)
                            weights_record.append(weights)
                            
                            portfolio_return = np.sum(annual_returns * weights)
                            portfolio_std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                            
                            results[0,i] = portfolio_return
                            results[1,i] = portfolio_std_dev
                            results[2,i] = (portfolio_return - 0.04) / portfolio_std_dev # Assuming 4% Risk-Free Rate
                            
                        # 4. Find the portfolio with the highest Sharpe Ratio
                        max_sharpe_idx = np.argmax(results[2])
                        opt_return = results[0, max_sharpe_idx]
                        opt_std = results[1, max_sharpe_idx]
                        opt_sharpe = results[2, max_sharpe_idx]
                        opt_weights = weights_record[max_sharpe_idx]
                        
                        mpt_col1, mpt_col2, mpt_col3 = st.columns(3)
                        mpt_col1.metric("Expected Annual Return", f"{opt_return * 100:.2f}%")
                        mpt_col2.metric("Expected Annual Risk (Volatility)", f"{opt_std * 100:.2f}%")
                        mpt_col3.metric("Maximum Sharpe Ratio", f"{opt_sharpe:.2f}")
                        
                        # Plot the Efficient Frontier
                        fig_mpt = px.scatter(
                            x=results[1,:], y=results[0,:], color=results[2,:],
                            labels={'x': 'Risk (Annualized Volatility)', 'y': 'Return (Annualized)', 'color': 'Sharpe Ratio'},
                            title="The Efficient Frontier (5,000 Simulated Portfolios)",
                            color_continuous_scale="Viridis"
                        )
                        # Add a star for the optimal portfolio
                        fig_mpt.add_trace(go.Scatter(x=[opt_std], y=[opt_return], mode='markers', marker=dict(color='red', size=15, symbol='star'), name='Optimal Portfolio'))
                        fig_mpt.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig_mpt, width='stretch')
                        
                        st.markdown("**Optimal Capital Allocation Weights:**")
                        weight_df = pd.DataFrame({"Asset": all_tickers_to_compare, "Weighting": opt_weights})
                        fig_weights = px.pie(weight_df, names="Asset", values="Weighting", hole=0.4, title="Mathematically Optimal Portfolio Distribution")
                        st.plotly_chart(fig_weights, width='stretch')
            else:
                st.warning("Please enter at least one Custom Peer to run the Portfolio Optimization engine.")
    else:
        st.error("🚨 Market entity not found or data retrieval failed.")