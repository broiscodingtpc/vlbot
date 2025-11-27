import asyncio
import logging
import random
from jupiter import JupiterClient
from config import RPC_URL
import utils
import base58

logger = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"

class VolumeTrader:
    def __init__(self, session_id: int, wallets: list, token_ca: str, strategy: str, notification_callback=None):
        self.session_id = session_id
        self.token_ca = token_ca
        self.strategy = strategy
        self.running = True
        self.wallets = wallets
        # Convert keypairs to base58 string format for JupiterClient
        self.clients = [JupiterClient(RPC_URL, w.to_base58_string()) for w in wallets]
        self.current_action = "SELL"  # START WITH SELL (vinde tokens prima data)
        self.trade_count = 0
        self.notification_callback = notification_callback
        
        # Volume Tracking
        self.session_volume_usd = 0.0
        self.last_report_time = 0
        self.volume_since_last_report = 0.0
        
        self.delays = {
            'slow': (120, 300),
            'medium': (60, 180),
            'fast': (30, 90)
        }
        self.trade_size_percent = 0.1  # Use only 10% of balance per trade (safer for Jupiter limits)
        
        # Minimum trade amounts (in UI)
        # After 0.1 SOL deposit, 0.05 SOL goes to dev, 0.05 SOL remains
        # Each wallet gets 0.01 SOL for gas, so we need to be careful with trades
        self.min_sol_trade = 0.01  # 0.01 SOL minimum (enough for gas + small trade)
        self.min_token_trade = 10  # 10 tokens minimum

    async def start(self):
        import time
        self.last_report_time = time.time()
        logger.info(f"Session {self.session_id}: Starting trading loop ({self.strategy}) - SELL FIRST")
        
        while self.running:
            try:
                # Check for 5-minute report
                current_time = time.time()
                if current_time - self.last_report_time >= 300:  # 300 seconds = 5 minutes
                    await self.send_periodic_report()
                    self.last_report_time = current_time
                    self.volume_since_last_report = 0.0

                client = random.choice(self.clients)
                
                # SELL = vinde tokens pentru SOL
                # BUY = cumpara tokens cu SOL
                if self.current_action == "SELL":
                    input_mint = self.token_ca  # Vinde tokens
                    output_mint = SOL_MINT
                else:
                    input_mint = SOL_MINT  # Cumpara tokens
                    output_mint = self.token_ca
                
                await self.execute_trade(client, input_mint, output_mint)
                
                # Toggle: SELL -> BUY -> SELL -> BUY
                self.current_action = "BUY" if self.current_action == "SELL" else "SELL"
                self.trade_count += 1
                
                delay = random.randint(*self.delays[self.strategy])
                logger.info(f"Session {self.session_id}: Sleeping {delay}s after {self.current_action}")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Session {self.session_id}: Error in trading loop: {e}")
                await asyncio.sleep(10)

    async def send_periodic_report(self):
        if self.notification_callback:
            msg = (
                f"📊 **KodeS Volume Bot - 5-Min Update**\n\n"
                f"🚀 **Volume Generated (Last 5m):** ${self.volume_since_last_report:,.2f}\n"
                f"📈 **Total Session Volume:** ${self.session_volume_usd:,.2f}\n"
                f"🔄 **Trades Executed:** {self.trade_count}\n\n"
                f"✅ Bot running smoothly!\n"
                f"💎 Generating volume with YOUR tokens - affordable & effective!\n\n"
                f"Next update in 5 minutes."
            )
            try:
                await self.notification_callback(msg)
            except Exception as e:
                logger.error(f"Failed to send report: {e}")

    async def execute_trade(self, client, input_mint, output_mint):
        pubkey_str = str(client.keypair.pubkey())
        
        if input_mint == SOL_MINT:
            balance = utils.get_balance(pubkey_str)
            decimals = 9
            min_trade = self.min_sol_trade
        else:
            balance = utils.get_token_balance(pubkey_str, input_mint)
            # Fetch real decimals from mint
            from solders.pubkey import Pubkey
            from config import RPC_URL
            from solana.rpc.api import Client as SolanaClient
            
            rpc_client = SolanaClient(RPC_URL)
            mint_pubkey = Pubkey.from_string(input_mint)
            mint_info = rpc_client.get_account_info(mint_pubkey)
            
            if mint_info.value and mint_info.value.data:
                try:
                    decimals = mint_info.value.data[44]  # Decimals at byte 44
                    logger.info(f"Token {input_mint[:8]}... has {decimals} decimals")
                except:
                    decimals = 6  # Default to 6 if can't read
                    logger.warning(f"Could not read decimals, defaulting to 6")
            else:
                decimals = 6
            
            min_trade = self.min_token_trade
            
        if balance == 0:
            logger.warning(f"Session {self.session_id}: Zero balance for {input_mint[:8]}...")
            return
        
        # Check if balance is above minimum
        if balance < min_trade:
            logger.warning(f"Session {self.session_id}: Balance {balance:.6f} below minimum {min_trade} for {input_mint[:8]}...")
            return

        # Calculate trade amount (10% of balance per trade)
        amount_ui = balance * self.trade_size_percent
        
        # Convert to raw amount (lamports/smallest unit)
        amount_raw = int(amount_ui * 10**decimals)
        
        # For SOL, leave some for gas fees (minimum 0.002 SOL for fees)
        if input_mint == SOL_MINT:
            min_reserve = 0.002  # Keep minimum reserve for transaction fees
            max_trade = (balance - min_reserve) * 10**9
            if amount_raw > max_trade:
                amount_raw = int(max_trade)
        
        if amount_raw <= 0:
            return
        
        logger.info(f"Session {self.session_id}: Trading {amount_ui:.6f} ({amount_raw} raw) {input_mint[:8]}... -> {output_mint[:8]}...")

        try:
            quote = client.get_quote(input_mint, output_mint, amount_raw)
            if not quote:
                logger.error(f"Session {self.session_id}: No quote received")
                return
                
            swap_txn = client.get_swap_transaction(quote)
            if not swap_txn:
                logger.error(f"Session {self.session_id}: No swap transaction received")
                return
                
            tx_sig = client.execute_swap(swap_txn['swapTransaction'])
            logger.info(f"Session {self.session_id}: Swap Executed! Sig: {tx_sig}")
            
            # Calculate Volume in USD
            # If input is SOL, use SOL price. If Token, use Token price.
            # Simplified: Use quote output amount if output is USDC/SOL, or estimate.
            # Better: Fetch SOL price once and use it if SOL is involved.
            
            try:
                # Estimate volume based on SOL value (since one side is always SOL)
                if input_mint == SOL_MINT:
                    sol_amount = amount_ui
                else:
                    # Output is SOL (approx)
                    sol_amount = int(quote.get('outAmount', 0)) / 10**9
                
                # Assume SOL = $240 (hardcoded for now or fetch)
                # Ideally fetch real price, but for speed we can use a fixed rate or fetch occasionally
                # Let's fetch from DexScreener if possible, or just use a standard rate for estimation
                # For now, let's use a rough estimate or fetch if we can. 
                # Actually, we can use the 'outAmount' if output is USDC, but it's not.
                # Let's use a fixed SOL price for volume estimation to avoid API spam, or fetch in __init__
                
                sol_price = 240.0 # Approximate
                trade_value_usd = sol_amount * sol_price
                
                self.session_volume_usd += trade_value_usd
                self.volume_since_last_report += trade_value_usd
                
                # Update DB
                from database import get_db, Session as DBSession
                db = next(get_db())
                db_session = db.query(DBSession).filter(DBSession.id == self.session_id).first()
                if db_session:
                    db_session.total_volume_generated += trade_value_usd
                    db.commit()
                    
            except Exception as e:
                logger.error(f"Error updating volume stats: {e}")
                
        except Exception as e:
            logger.error(f"Session {self.session_id}: Swap Failed: {e}")

    def stop(self):
        self.running = False
