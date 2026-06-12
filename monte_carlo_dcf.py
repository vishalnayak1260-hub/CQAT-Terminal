import numpy as np
import pandas as pd
from sqlalchemy import create_engine
import time

print("Initiating Monte Carlo DCF Simulation Engine...")
print("-" * 50)

# ==========================================
# 1. CONNECT TO THE VAULT
# ==========================================
engine = create_engine('sqlite:///cqat_vault.db', echo=False)

# Fetch the most recent closing price for SYNGENE.NS to compare against our simulation
query = "SELECT close_price FROM fact_market WHERE ticker = 'SYNGENE.NS' ORDER BY date DESC LIMIT 1"
df_price = pd.read_sql(query, engine)
current_market_price = df_price['close_price'].iloc[0]

# ==========================================
# 2. THE FINANCIAL ASSUMPTIONS (SYNGENE.NS)
# ==========================================
# These are proxy assumptions for the HBeAg pipeline asset
iterations = 10000
years = 5
wacc = 0.10                 # 10% Weighted Average Cost of Capital
shares_outstanding = 400    # Example: 400 Million shares
terminal_multiple = 15      # EV/EBITDA exit multiple

# Biological Edge (Imported from Phase 2 PoA Engine)
poa_score = 0.73  

# ==========================================
# 3. THE STOCHASTIC SIMULATION (10,000 Iterations)
# ==========================================
print(f"Simulating {iterations:,} clinical and financial realities for SYNGENE.NS...")
time.sleep(1) # Dramatic pause for terminal effect

# 3A. Simulate Clinical Trial Success/Failure (Binary Matrix)
# A binomial distribution tests 10,000 trials with a 73% chance of success
clinical_outcomes = np.random.binomial(1, poa_score, iterations)

# 3B. Simulate Revenue Trajectories
# We assume base revenue is 5,000M INR, but randomize it using standard deviation
simulated_revenues = np.random.normal(loc=5000, scale=800, size=(iterations, years))

# 3C. Calculate Free Cash Flow (Assuming a 20% margin)
fcf_matrix = simulated_revenues * 0.20

# 3D. Execute the Discounted Cash Flow (DCF) Math
present_value_array = np.zeros(iterations)

for i in range(iterations):
    # If the trial fails (0), the asset generates 0 revenue
    if clinical_outcomes[i] == 0:
        present_value_array[i] = 0
    else:
        # If the trial succeeds (1), we calculate the NPV of the cash flows
        npv = 0
        for t in range(years):
            npv += fcf_matrix[i, t] / ((1 + wacc) ** (t + 1))
            
        # Add Terminal Value to the final year
        terminal_value = (fcf_matrix[i, -1] * terminal_multiple) / ((1 + wacc) ** years)
        npv += terminal_value
        
        # Divide by shares outstanding to get the Per Share Value
        present_value_array[i] = npv / shares_outstanding

# ==========================================
# 4. STATISTICAL ANALYSIS
# ==========================================
# Filter out the zero-value failures to find the value of the successful realities
successful_paths = present_value_array[present_value_array > 0]

# Calculate Percentiles
worst_case = np.percentile(successful_paths, 5)   # Bottom 5%
base_case = np.median(successful_paths)           # 50th Percentile
best_case = np.percentile(successful_paths, 95)   # Top 5%

print("\n" + "=" * 50)
print(" MONTE CARLO DCF OUTPUT: SYNGENE.NS (HBeAg Asset)")
print("=" * 50)
print(f"Current Market Price:    ₹{current_market_price:.2f}")
print("-" * 50)
print(f"Implied Worst Case (5%): ₹{worst_case:.2f} (Trial Succeeds, Poor Sales)")
print(f"Implied Base Case (50%): ₹{base_case:.2f} (Expected Value)")
print(f"Implied Best Case (95%): ₹{best_case:.2f} (Blockbuster Status)")
print("=" * 50)

# Calculate the Arbitrage Gap
arbitrage_gap = ((base_case - current_market_price) / current_market_price) * 100
print(f"Algorithm Verdict: The asset is mispriced by {arbitrage_gap:.2f}% based on structural PoA.")
print("-" * 50)