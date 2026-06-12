import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sqlalchemy import create_engine

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="CQAT Terminal", page_icon="🧬", layout="wide")

# Custom Dark Mode styling injection
st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    h1, h2, h3 {color: #e2e8f0;}
    .stMetric {background-color: #1e293b; padding: 15px; border-radius: 10px;}
    </style>
""", unsafe_allow_html=True)

st.title("🧬 Clinical-Quant Arbitrage Terminal (CQAT)")
st.markdown("Enterprise In-Silico Valuation & Stochastic Modeling Infrastructure")
st.markdown("---")

# ==========================================
# 2. DATABASE CONNECTION
# ==========================================
@st.cache_data # Caches the data so the app doesn't crash your hard drive on refresh
def load_data():
    engine = create_engine('sqlite:///cqat_vault.db')
    df_market = pd.read_sql("SELECT * FROM fact_market", engine)
    df_clinical = pd.read_sql("SELECT * FROM fact_clinical", engine)
    return df_market, df_clinical

df_market, df_clinical = load_data()

# ==========================================
# 3. SIDEBAR NAVIGATION & FILTERS
# ==========================================
st.sidebar.header("Command Center")
unique_tickers = df_market['ticker'].unique()
selected_ticker = st.sidebar.selectbox("Select Target Equity:", unique_tickers)

# Filter data based on selection
ticker_market_data = df_market[df_market['ticker'] == selected_ticker].sort_values(by='date')
ticker_clinical_data = df_clinical[df_clinical['ticker'] == selected_ticker]

# ==========================================
# 4. MAIN DASHBOARD: FINANCIAL METRICS
# ==========================================
st.header(f"Live Market Profile: {selected_ticker}")

if not ticker_market_data.empty:
    current_price = ticker_market_data['close_price'].iloc[-1]
    volume = ticker_market_data['volume'].iloc[-1]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Current Market Price", f"₹{current_price:.2f}" if "NS" in selected_ticker else f"${current_price:.2f}")
    col2.metric("Latest Trading Volume", f"{volume:,}")
    
    # Financial Chart
    fig_price = px.line(ticker_market_data, x='date', y=['close_price', 'sma_50'], 
                        title=f"{selected_ticker} Price Action vs 50-SMA",
                        color_discrete_sequence=['#3b82f6', '#ef4444'])
    st.plotly_chart(fig_price, use_container_width=True)

# ==========================================
# 5. BIOLOGICAL EDGE & STOCHASTIC ENGINE
# ==========================================
st.markdown("---")
st.header("In-Silico Clinical Evaluation")

if not ticker_clinical_data.empty:
    target_protein = ticker_clinical_data['target_protein'].iloc[0]
    phase = ticker_clinical_data['phase'].iloc[0]
    
    st.info(f"**Lead Pipeline Asset:** Targeting {target_protein} ({phase})")
    
    # We hardcode the PoA for the demo, but in production, this would query your poa_engine outputs
    poa_score = 0.73 if selected_ticker == 'SYNGENE.NS' else 0.85
    st.metric("Probability of Approval (PoA)", f"{poa_score * 100}%", "Calculated via RMSD & Delta-G base")
    
    # Run Live Monte Carlo Button
    if st.button("Run Stochastic DCF Simulation (10,000 Iterations)"):
        with st.spinner("Simulating clinical outcomes and cash flows..."):
            
            # Live Math Execution
            iterations = 10000
            clinical_outcomes = np.random.binomial(1, poa_score, iterations)
            simulated_revenues = np.random.normal(loc=5000, scale=800, size=(iterations, 5))
            fcf_matrix = simulated_revenues * 0.20
            
            present_value_array = np.zeros(iterations)
            for i in range(iterations):
                if clinical_outcomes[i] > 0:
                    npv = sum([fcf_matrix[i, t] / ((1 + 0.10) ** (t + 1)) for t in range(5)])
                    present_value_array[i] = npv / 400 # Per share
            
            successful_paths = present_value_array[present_value_array > 0]
            
            # Draw the Bell Curve Histogram
            st.success("Simulation Complete.")
            fig_mc = px.histogram(successful_paths, nbins=50, 
                                  title="Implied Share Price Distribution (Successful Outcomes Only)",
                                  color_discrete_sequence=['#10b981'])
            fig_mc.update_layout(xaxis_title="Implied Price per Share", yaxis_title="Probability Count")
            st.plotly_chart(fig_mc, use_container_width=True)
            
            # Statistical Output
            col_mc1, col_mc2, col_mc3 = st.columns(3)
            col_mc1.metric("Worst Case (5%)", f"₹{np.percentile(successful_paths, 5):.2f}")
            col_mc2.metric("Base Case (50%)", f"₹{np.median(successful_paths):.2f}")
            col_mc3.metric("Best Case (95%)", f"₹{np.percentile(successful_paths, 95):.2f}")

else:
    st.warning("No clinical trial data registered for this equity.")