import pandas as pd
from sqlalchemy import create_engine

print("Accessing CQAT Vault...")
print("-" * 50)

# Connect to the database
engine = create_engine('sqlite:///cqat_vault.db')

# Write a professional SQL JOIN query
# We are asking the database to merge the company directory with the market data,
# specifically pulling the last 5 days of data for Vertex Pharmaceuticals.
sql_query = """
    SELECT 
        c.company_name, 
        m.date, 
        m.close_price, 
        m.sma_50, 
        m.volume
    FROM fact_market m
    JOIN dim_company c ON m.ticker = c.ticker
    WHERE m.ticker = 'VRTX'
    ORDER BY m.date DESC
    LIMIT 5;
"""

# Execute the query and load it into a Pandas DataFrame for beautiful formatting
df = pd.read_sql(sql_query, engine)

if df.empty:
    print("[!] ERROR: The vault is empty or the query failed.")
else:
    print("[+] SUCCESS: Data extracted flawlessly. Here are the latest 5 days for VRTX:")
    print("\n")
    print(df.to_string(index=False))

print("\n" + "-" * 50)