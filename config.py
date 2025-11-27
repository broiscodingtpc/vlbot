import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = 8342160274  # Owner/Dev ID (hardcoded)

# Solana
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
DEV_WALLET_ADDRESS = os.getenv("DEV_WALLET_ADDRESS", "YourDevWalletAddressHere")

# Fees
FEE_SOL_PERCENT = 0.5  # 50% of deposited SOL goes to dev
FEE_TOKEN_PERCENT = 0.0  # 0% - no fee on tokens, only SOL

# Database
# Railway provides PostgreSQL via DATABASE_URL environment variable
# Fallback to SQLite for local development
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    # PostgreSQL on Railway (or other cloud providers)
    # Railway provides DATABASE_URL in format: postgresql://user:pass@host:port/dbname
    # SQLAlchemy needs postgresql:// but Railway might provide postgres://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    DB_PATH = DATABASE_URL
else:
    # SQLite for local development
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'volumebot.db')
    # Ensure directory exists
    db_dir = os.path.dirname(DATABASE_PATH) if os.path.dirname(DATABASE_PATH) else '.'
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    DB_PATH = f"sqlite:///{DATABASE_PATH}"
