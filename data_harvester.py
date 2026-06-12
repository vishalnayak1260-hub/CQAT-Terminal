import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import time
from datetime import datetime

# Import the database schemas we built in the core file
from database_core import Company, MarketData

print("Initiating Financial Data Harvester...")
print("-" * 50)

# ==========================================
# 1. CONNECT TO THE VAULT
# ==========================================
# This opens the door to the database file you created
engine = create_engine('sqlite:///cqat_vault.db', echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# ==========================================
# 2. DEFINE THE TARGET UNIVERSE
# ==========================================
# For Phase 1 testing, we use a highly targeted mix of Global and Domestic targets
target_universe = {
    'VRTX': 'Vertex Pharmaceuticals',
    'AMGN': 'Amgen Inc.',
    'SUNPHARMA.NS': 'Sun Pharmaceutical',
    'SYNGENE.NS': 'Syngene International'
}

# ==========================================
# 3. POPULATE THE DIRECTORY (dim_company)
# ==========================================
print("Verifying Company Directory...")
for ticker, name in target_universe.items():
    # Check if the company already exists in the database
    exists = session.query(Company).filter_by(ticker=ticker).first()
    
    if not exists:
        print(f"  [+] Adding {ticker} to the master directory.")
        new_company = Company(ticker=ticker, company_name=name, sector='Healthcare')
        session.add(new_company)

# Save the directory updates
session.commit()

# ==========================================
# 4. INGEST MARKET DATA (fact_market)
# ==========================================
for ticker in target_universe.keys():
    print(f"\nScraping and processing API data for {ticker}...")
    
    try:
        # Download exactly 1 year of daily historical data
        df = yf.download(ticker, period="1y", progress=False)
        
        if df.empty:
            print(f"  [!] WARNING: No data found for {ticker}.")
            continue
            
        # Flatten the complex Yahoo Finance MultiIndex formatting
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Calculate the 50-Day Simple Moving Average
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        
        # Drop the first 50 days where the SMA cannot be calculated
        df = df.dropna()
        
        # Package the data for database insertion
        records_to_insert = []
        for index, row in df.iterrows():
            record = MarketData(
                ticker=ticker,
                date=index.date(),
                close_price=float(row['Close']),
                volume=int(row['Volume']),
                sma_50=float(row['SMA_50'])
            )
            records_to_insert.append(record)
            
        # Bulk insert all records into the database instantly
        session.bulk_save_objects(records_to_insert)
        session.commit()
        
        print(f"  [$$$] SUCCESS: Injected {len(records_to_insert)} days of financial metrics into the vault.")
        
    except Exception as e:
        print(f"  [!] ERROR: Pipeline failure for {ticker}. Reason: {e}")
        session.rollback() # Protects the database if a crash happens
        
    # Rate Limiting
    time.sleep(1)

print("-" * 50)
print("Data Harvester Execution Complete. The Vault is updated.")