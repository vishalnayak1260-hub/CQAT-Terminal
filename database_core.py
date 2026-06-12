from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ==========================================
# TABLE 1: dim_company (The Directory)
# ==========================================
class Company(Base):
    __tablename__ = 'dim_company'
    
    ticker = Column(String, primary_key=True)
    company_name = Column(String)
    sector = Column(String)
    
    # Establish links to BOTH the financial and clinical data
    market_data = relationship("MarketData", back_populates="company")
    clinical_trials = relationship("ClinicalTrial", back_populates="company")

# ==========================================
# TABLE 2: fact_market (Financial Data)
# ==========================================
class MarketData(Base):
    __tablename__ = 'fact_market'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey('dim_company.ticker'))
    date = Column(Date)
    close_price = Column(Float)
    volume = Column(Integer)
    sma_50 = Column(Float)
    
    company = relationship("Company", back_populates="market_data")

# ==========================================
# TABLE 3: fact_clinical (Biological Data) - NEW
# ==========================================
class ClinicalTrial(Base):
    __tablename__ = 'fact_clinical'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey('dim_company.ticker'))
    nct_id = Column(String, unique=True) # The Official Government Trial ID
    phase = Column(String)               # e.g., Phase 2, Phase 3
    target_disease = Column(String)      # e.g., Cystic Fibrosis, Oncology
    status = Column(String)              # e.g., Recruiting, Completed
    target_protein = Column(String)
    
    company = relationship("Company", back_populates="clinical_trials")

# ==========================================
# THE DATABASE ENGINE EXECUTION
# ==========================================
if __name__ == "__main__":
    print("Upgrading CQAT Relational Database Schema...")
    print("-" * 50)
    
    engine = create_engine('sqlite:///cqat_vault.db', echo=False)
    
    # This will detect the new 'fact_clinical' table and safely add it to your existing vault
    # without destroying the 800 rows of financial data you just downloaded.
    Base.metadata.create_all(engine)
    
    print("[+] SUCCESS: Clinical Trial schema (Pipeline B) added to the Vault.")