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
    industry = Column(String)
    
    market_data = relationship("MarketData", back_populates="company", cascade="all, delete-orphan")

# ==========================================
# TABLE 2: fact_market (Financial Historical Data)
# ==========================================
class MarketData(Base):
    __tablename__ = 'fact_market'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey('dim_company.ticker'))
    date = Column(Date)
    close_price = Column(Float)
    volume = Column(Integer)
    sma_50 = Column(Float)
    sma_200 = Column(Float)  # Added for institutional trend analysis
    
    company = relationship("Company", back_populates="market_data")

# ==========================================
# THE DATABASE ENGINE EXECUTION
# ==========================================
if __name__ == "__main__":
    print("Initializing Junior Analyst Terminal Database Vault...")
    engine = create_engine('sqlite:///cqat_vault.db', echo=False)
    Base.metadata.create_all(engine)
    print("[+] SUCCESS: Core financial schema initialized.")