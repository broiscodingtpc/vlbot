# KodeS Volume Bot

Solana Volume Generation Bot - Generate high trading volume using your tokens on Solana DEX.

## Features

- 🔥 **Token-Based Volume**: Uses YOUR tokens for volume generation, not expensive SOL
- 💰 **Ultra Affordable**: Generate massive volume with minimal cost
- 🎯 **Smart Trading**: Randomized patterns that look 100% organic
- 🔐 **Multi-Wallet System**: Unique wallets prevent detection & clustering
- ⚙️ **Fully Automated**: Set it and forget it - we handle everything
- 📊 **Real-Time Updates**: Performance reports every 5 minutes

## How It Works

1. User deposits **0.1 SOL + Tokens** to the bot's deposit wallet
2. Bot collects **0.05 SOL fee** (50% of SOL deposit)
3. Bot creates **3 sub-wallets** and distributes tokens
4. Bot executes **SELL → BUY → SELL → BUY** cycles continuously
5. Volume is generated on DEX (Jupiter/Raydium)

## Setup

### Prerequisites

- Python 3.9+
- Telegram Bot Token
- Solana RPC URL (Helius recommended)
- Dev Wallet Address (for fee collection)

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd volumebot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
RPC_URL=https://mainnet.helius-rpc.com/?api-key=your_api_key
DEV_WALLET_ADDRESS=your_dev_wallet_address
DATABASE_PATH=volumebot.db
```

4. Run the bot:
```bash
python bot.py
```

## Railway Deployment

### Step 1: Push to GitHub

1. Initialize git repository (if not already):
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

### Step 2: Deploy on Railway

1. Go to [Railway](https://railway.app) and sign in
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add environment variables in Railway dashboard:
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
   - `RPC_URL` - Your Solana RPC URL (Helius recommended)
   - `DEV_WALLET_ADDRESS` - Your dev wallet for fee collection
   - `DATABASE_PATH` - `volumebot.db` (or leave default)

5. Railway will automatically detect the `Procfile` and deploy

### Environment Variables

Required environment variables:

- `TELEGRAM_BOT_TOKEN` - Telegram bot token from @BotFather
- `RPC_URL` - Solana RPC endpoint (default: mainnet-beta)
- `DEV_WALLET_ADDRESS` - Wallet address for fee collection
- `DATABASE_PATH` - Path to SQLite database (default: `volumebot.db`)

## Usage

1. Start the bot: `/start` in Telegram
2. Create a new session: Click "🚀 Start Volume Session"
3. Enter your token contract address (CA)
4. Select trading strategy:
   - 🐢 **Slow**: 120-300s delays (organic)
   - 🐇 **Medium**: 60-180s delays (balanced)
   - 🚀 **Fast**: 30-90s delays (aggressive)
5. Deposit **0.1 SOL + Tokens** to the provided wallet address
6. Click "🔄 Check Deposit" to start trading

## Commands

- `/start` - Start the bot / Show main menu
- `/withdraw <address>` - Stop trading and withdraw all funds

### Admin Commands

- `/admin_stats` - Show global statistics
- `/admin_sessions` - List all sessions
- `/admin_sweep_all` - Sweep all funds to dev wallet

## Trading Strategy

The bot alternates between:
- **SELL**: Sells tokens for SOL
- **BUY**: Buys tokens with SOL

Each trade uses **10% of balance** to ensure longevity.

## Fees

- **SOL Fee**: 50% of deposited SOL (0.05 SOL from 0.1 SOL deposit)
- **Token Fee**: 0% (no fee on tokens)

## Database

The bot uses SQLite database to store:
- Users
- Sessions
- Sub-wallets
- Trading statistics

Database file: `volumebot.db` (configurable via `DATABASE_PATH`)

## Security Notes

⚠️ **Important**: 
- Private keys are stored in plain text in the database (for MVP)
- In production, encrypt private keys before storing
- Never commit `.env` file or database to git
- Use strong RPC endpoints with API keys

## Support

For issues or questions, contact the admin.

## License

Private - All rights reserved

