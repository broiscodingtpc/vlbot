import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', '0'))
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID') # Channel ID for announcements

# Wallet
DEV_WALLET_ADDRESS = os.getenv('DEV_WALLET_ADDRESS', 'YourDevWalletAddressHere')

# Database
DB_PATH = 'sqlite:///volumebot.db'

# Solana / Jupiter
RPC_URL = os.getenv('RPC_URL', 'https://api.mainnet-beta.solana.com')
JUPITER_API_URL = "https://quote-api.jup.ag/v6" # V6 API

# Fees & Settings
FEE_SOL_PERCENT = 0.50  # 50% of deposited SOL
FEE_SALE_PERCENT = 0.10 # 10% of Token Sale Proceeds (in SOL)
SOL_BUFFER = 0.005      # Buffer for gas
MIN_TRADE_SOL_THRESHOLD = 0.01
SOL_PRICE_USD = 240.0   # Approximate, can be fetched dynamically
