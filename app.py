import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
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
    .stTabs [data-baseweb="tab"] {font-size: 16px; font-weight: 600; color: #94a3b8;}
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

def resolve_company_name(query):
    """Converts natural language queries into clean market ticker symbols."""
    clean_query = query.strip()
    if not clean_query:
        return ""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={clean_query}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        if 'quotes' in data and len(data['quotes']) > 0:
            for quote in data['quotes']:
                if quote.get('quoteType') == 'EQUITY':
                    return quote.get('symbol')
            return data['quotes'][0].get('symbol')
    except Exception:
        pass
    return clean_query.upper()

def fetch_and_store_financials(ticker_symbol):
    """Downloads historical data and initializes record structures in the local SQLite vault."""
    session = Session()
    exists = session.query(Company).filter_by(ticker=ticker_symbol).first()
    if exists:
        session.close()
        return True
        
    try:
        stock_info = yf.Ticker(ticker_symbol)
        company_name = stock_info.info.get('shortName', ticker_symbol)
        sector = stock_info.info.get('sector', 'General')
        industry = stock_info.info.get('industry', 'General')
        
        new_company = Company(ticker=ticker_symbol, company_name=company_name, sector=sector, industry=industry)
        session.add(new_company)
        
        df = yf.download(ticker_symbol, period="1y", progress=False)
        if df.empty:
            session.close()
            return False
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df = df.dropna()
        
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

# ==========================================
# 3. INTERFACE COMMAND SIDEBAR
# ==========================================
st.sidebar.header("Command Center")
raw_input = st.sidebar.text_input("Target Asset Name / Ticker:", "Biocon")
search_button = st.sidebar.button("Run Financial Intelligence Suite")

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Custom Peer Comps")
st.sidebar.markdown("Enter plain company names or raw codes separated by commas:")
peer_input = st.sidebar.text_input("Peer Tickers / Names:", "Syngene, Dr Reddy, Cipla")

# ==========================================
# 4. EXECUTION MATRIX
# ==========================================
if search_button or raw_input:
    selected_ticker = resolve_company_name(raw_input)
    
    if fetch_and_store_financials(selected_ticker):
        df_market = pd.read_sql(f"SELECT * FROM fact_market WHERE ticker = '{selected_ticker}'", engine)
        
        try:
            raw_ticker = yf.Ticker(selected_ticker)
            info = raw_ticker.info
            full_name = info.get('longName', info.get('shortName', selected_ticker))
            currency = info.get('currency', 'USD')
            curr_sym = "₹" if currency == "INR" else "$"
        except:
            info = {}
            full_name = selected_ticker
            curr_sym = "$"

        st.header(f"{full_name} ({selected_ticker})")
        st.markdown(f"**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')} | **Exchange:** {info.get('exchange', 'N/A')}")
        
        tab_market, tab_comps, tab_dcf, tab_dupont = st.tabs([
            "📈 Market Performance & Multiples", 
            "📊 Comparable Peer Benchmarking", 
            "🔮 Intrinsic 3-Scenario DCF Model",
            "🔍 DuPont Profitability Analysis"
        ])
        
        # ----------------------------------------------------
        # TAB 1: MARKET PERFORMANCE & MULTIPLES
        # ----------------------------------------------------
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

        # ----------------------------------------------------
        # TAB 2: COMPARABLE COMPANY ANALYSIS (NLP BATCH)
        # ----------------------------------------------------
        with tab_comps:
            st.subheader("Relative Valuation Matrix (Peer Comps)")
            st.markdown("Compares corporate multiples to identify relative market premiums or discount entry points.")
            
            raw_peer_strings = [p.strip() for p in peer_input.split(",") if p.strip()]
            resolved_peers = []
            
            with st.spinner("Resolving peer identities..."):
                for raw_p in raw_peer_strings:
                    ticker_resolved = resolve_company_name(raw_p)
                    if ticker_resolved and ticker_resolved not in resolved_peers:
                        resolved_peers.append(ticker_resolved)
            
            all_tickers_to_compare = [selected_ticker] + resolved_peers
            st.caption(f"Active Peer Tracking Array: {', '.join(all_tickers_to_compare)}")
            
            comps_data = []
            with st.spinner("Extracting operational metrics across peer group..."):
                for t in all_tickers_to_compare:
                    try:
                        p_ticker = yf.Ticker(t)
                        p_info = p_ticker.info
                        comps_data.append({
                            "Ticker": t,
                            "Company Name": p_info.get('shortName', t),
                            "P/E Ratio": p_info.get('trailingPE', None),
                            "EV/EBITDA": p_info.get('enterpriseToEbitda', None),
                            "P/B Ratio": p_info.get('priceToBook', None),
                            "Net Margin (%)": p_info.get('profitMargins', 0) * 100 if p_info.get('profitMargins') else None
                        })
                    except:
                        pass
            
            if comps_data:
                df_comps = pd.DataFrame(comps_data)
                st.dataframe(df_comps.style.highlight_max(axis=0, subset=['Net Margin (%)']).format({
                    "P/E Ratio": "{:.2f}x", "EV/EBITDA": "{:.2f}x", "P/B Ratio": "{:.2f}x", "Net Margin (%)": "{:.2f}%"
                }), use_container_width=True)
                
                try:
                    avg_pe = df_comps["P/E Ratio"].mean()
                    target_pe = df_comps[df_comps["Ticker"] == selected_ticker]["P/E Ratio"].values[0]
                    if target_pe and avg_pe:
                        variance = ((target_pe - avg_pe) / avg_pe) * 100
                        status_label = "Premium" if variance > 0 else "Discount"
                        st.info(f"💡 Analytics Insight: **{selected_ticker}** trades at a **{abs(variance):.1f}% {status_label}** relative to the specified peer group average P/E of **{avg_pe:.2f}x**.")
                except:
                    pass

        # ----------------------------------------------------
        # TAB 3: INTRINSIC 3-SCENARIO DCF MODEL
        # ----------------------------------------------------
        with tab_dcf:
            st.subheader("Structured 3-Scenario Free Cash Flow Engine")
            st.markdown("Calculates intrinsic asset value by applying user-defined growth pathways to trailing operational cash flows.")
            
            raw_rev = info.get('totalRevenue', 1000000000)
            raw_fcf = info.get('freeCashflow', raw_rev * 0.10)
            fcf_base_millions = float(raw_fcf / 1000000) if raw_fcf else (raw_rev * 0.12) / 1000000
            
            st.markdown(f"**Baseline Parameter:** TTM Free Cash Flow captured at **{curr_sym}{fcf_base_millions:.2f} Million**.")
            
            dcf_col1, dcf_col2, dcf_col3 = st.columns(3)
            wacc_input = dcf_col1.slider("Discount Rate (WACC %)", 6.0, 16.0, 10.0, step=0.5) / 100
            terminal_growth = dcf_col2.slider("Terminal Perpetuity Growth (% Growth)", 1.0, 6.0, 4.0, step=0.2) / 100
            
            shares_raw = info.get('sharesOutstanding', 50000000)
            shares_outstanding = dcf_col3.number_input("Shares Outstanding (Millions)", value=float(shares_raw / 1000000) if shares_raw else 100.0, min_value=1.0)
            
            scenarios = {
                "Bear Case (Conservative)": {"growth": 0.04, "color": "#ef4444"},
                "Base Case (Market Consensus)": {"growth": 0.08, "color": "#3b82f6"},
                "Bull Case (Aggressive Expansion)": {"growth": 0.14, "color": "#10b981"}
            }
            
            dcf_results = {}
            for name, config in scenarios.items():
                g = config["growth"]
                projected_cfs = [fcf_base_millions * ((1 + g) ** year) for year in range(1, 6)]
                pv_cfs = [projected_cfs[t] / ((1 + wacc_input) ** (t + 1)) for t in range(5)]
                terminal_value = (projected_cfs[-1] * (1 + terminal_growth)) / (wacc_input - terminal_growth)
                pv_terminal_value = terminal_value / ((1 + wacc_input) ** 5)
                
                total_intrinsic_value = sum(pv_cfs) + pv_terminal_value
                per_share_target = total_intrinsic_value / shares_outstanding
                dcf_results[name] = per_share_target
            
            df_dcf_plot = pd.DataFrame(list(dcf_results.items()), columns=["Scenario", "Target Price Per Share"])
            fig_dcf = px.bar(df_dcf_plot, x="Scenario", y="Target Price Per Share", text_auto=".2f",
                             title="Calculated Intrinsic Target Values Across Strategic Corporate Scenarios",
                             color="Scenario", color_discrete_map={k: v["color"] for k, v in scenarios.items()})
            st.plotly_chart(fig_dcf, width='stretch')
            
            c_price = df_market['close_price'].iloc[-1]
            st.markdown(f"**Current Market Trading Price:** {curr_sym}{c_price:.2f}")
            
            dcf_metrics_cols = st.columns(3)
            idx = 0
            for name, val in dcf_results.items():
                upside = ((val - c_price) / c_price) * 100
                dcf_metrics_cols[idx].metric(name, f"{curr_sym}{val:.2f}", f"{upside:+.1f}% Implied Edge")
                idx += 1

        # ----------------------------------------------------
        # TAB 4: DUPONT PROFITABILITY ANALYSIS
        # ----------------------------------------------------
        with tab_dupont:
            st.subheader("3-Stage DuPont Accounting Deconstruction")
            st.markdown("Deconstructs corporate Return on Equity (ROE) to evaluate if returns are driven by profitability, operational velocity, or financial leverage.")
            
            net_income = info.get('netIncomeToCommon', None)
            total_assets = info.get('totalAssets', None)
            total_equity = info.get('totalStockholderEquity', None)
            revenue = info.get('totalRevenue', None)
            
            if net_income and total_assets and total_equity and revenue:
                net_profit_margin = net_income / revenue
                asset_turnover = revenue / total_assets
                equity_multiplier = total_assets / total_equity
                calculated_roe = net_profit_margin * asset_turnover * equity_multiplier
                
                dp_col1, dp_col2, dp_col3, dp_col4 = st.columns(4)
                dp_col1.metric("Net Profit Margin (Efficiency)", f"{net_profit_margin * 100:.2f}%")
                dp_col2.metric("Asset Turnover (Operational Speed)", f"{asset_turnover:.2f}x")
                dp_col3.metric("Equity Multiplier (Financial Leverage)", f"{equity_multiplier:.2f}x")
                dp_col4.metric("Deconstructed Return on Equity", f"{calculated_roe * 100:.2f}%")
                
                st.markdown(" ")
                if equity_multiplier > 2.5:
                    st.warning("⚠️ Risk Warning: This business demonstrates a high Equity Multiplier. A significant portion of its structural return vector is driven by capital structure debt leverage rather than pure manufacturing or commercial pricing power margins.")
                else:
                    st.success("✅ Operational Health: The corporate leverage profile is balanced, showing that returns are backed by functional operational assets rather than aggressive financial engineering.")
            else:
                st.warning("Complete financial statements are missing for this specific ticker code profile to calculate a full 3-Stage DuPont deconstruction.")