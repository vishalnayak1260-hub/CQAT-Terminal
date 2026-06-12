from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import time

# Import the database schemas
from database_core import Company, ClinicalTrial

print("Initiating Clinical API Harvester...")
print("-" * 50)

# ==========================================
# 1. CONNECT TO THE VAULT
# ==========================================
engine = create_engine('sqlite:///cqat_vault.db', echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# ==========================================
# 2. THE CLINICAL TRIAL PAYLOAD
# ==========================================
# This acts as our data feed from the US ClinicalTrials.gov registry.
# We are specifically logging the target proteins so our structural 
# biology engine can calculate binding affinities in Phase 2.

clinical_data_feed = [
    {
        'ticker': 'VRTX',
        'nct_id': 'NCT04056000',
        'phase': 'Phase 3',
        'target_disease': 'Cystic Fibrosis',
        'status': 'Recruiting',
        'target_protein': 'CFTR'
    },
    {
        'ticker': 'AMGN',
        'nct_id': 'NCT03600883',
        'phase': 'Phase 2',
        'target_disease': 'Non-Small Cell Lung Cancer',
        'status': 'Active',
        'target_protein': 'KRAS G12C'
    },
    {
        'ticker': 'SYNGENE.NS',
        'nct_id': 'NCT05001234', # Synthesized ID for architecture testing
        'phase': 'Phase 2',
        'target_disease': 'Chronic Hepatitis B',
        'status': 'Recruiting',
        'target_protein': 'Hepatitis B Virus e-antigen (HBeAg) complex'
    },
    {
        'ticker': 'SUNPHARMA.NS',
        'nct_id': 'NCT04400122',
        'phase': 'Phase 3',
        'target_disease': 'Severe Plaque Psoriasis',
        'status': 'Completed',
        'target_protein': 'IL-23'
    }
]

# ==========================================
# 3. INGESTION PROTOCOL
# ==========================================
print("Pinging Clinical Registries and linking molecular targets...")

inserted_count = 0

for trial in clinical_data_feed:
    # First, verify the company actually exists in our financial directory
    company_exists = session.query(Company).filter_by(ticker=trial['ticker']).first()
    
    if company_exists:
        # Check to prevent duplicate trial entries
        trial_exists = session.query(ClinicalTrial).filter_by(nct_id=trial['nct_id']).first()
        
        if not trial_exists:
            new_trial = ClinicalTrial(
                ticker=trial['ticker'],
                nct_id=trial['nct_id'],
                phase=trial['phase'],
                target_disease=trial['target_disease'],
                status=trial['status'],
                target_protein=trial['target_protein']
                # Note: We will expand the schema to hold the raw protein strings in Phase 2.
            )
            session.add(new_trial)
            inserted_count += 1
            print(f"  [+] SUCCESS: Logged Trial {trial['nct_id']} for {trial['ticker']} (Target: {trial['target_protein']})")
        else:
            print(f"  [!] SKIP: Trial {trial['nct_id']} is already in the vault.")
    else:
        print(f"  [!] ERROR: Cannot log trial. {trial['ticker']} is missing from the financial directory.")
        
    time.sleep(0.5) # Simulate API rate limiting

session.commit()

print("-" * 50)
print(f"Clinical Harvester Complete. {inserted_count} critical biological catalysts securely logged.")