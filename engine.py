import asyncio
import logging
import random
from jupiter import JupiterClient
from config import RPC_URL, MIN_TRADE_SOL_THRESHOLD, SOL_PRICE_USD
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
        # solders.keypair.Keypair uses pubkey().to_base58() or str(pubkey())
        self.clients = [JupiterClient(RPC_URL, str(w.pubkey())) for w in wallets]
        self.current_action = "BUY"  # START WITH BUY (sub-wallets have SOL, need to buy tokens first)
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
        self.min_sol_trade = MIN_TRADE_SOL_THRESHOLD  # Use config constant
        self.min_token_trade = 10  # 10 tokens minimum
        self.sol_price_usd = SOL_PRICE_USD  # SOL price for volume calculation

    async def start(self):
        import time
        self.last_report_time = time.time()
        logger.info(f"Session {self.session_id}: Starting trading loop ({self.strategy}) - BUY FIRST (sub-wallets have SOL)")
        
        cycle = 1
        
        while self.running:
            try:
                # Check if we have sufficient capital to continue trading
                can_trade = await self._check_sufficient_capital()
                if not can_trade:
                    logger.info(f"Session {self.session_id}: Insufficient capital. Stopping trading.")
                    if self.notification_callback:
                        await self.notification_callback(
                            f"⏹️ **Trading Stopped - Funds Exhausted**\n\n"
                            f"📊 **Final Stats:**\n"
                            f"• Total Volume: ${self.session_volume_usd:,.2f}\n"
                            f"• Total Trades: {self.trade_count}\n"
                            f"• Cycles Completed: {cycle}\n\n"
                            f"💡 Session will be finalized. Remaining funds will be swept."
                        )
                    break
                
                # Check for 5-minute report
                current_time = time.time()
                if current_time - self.last_report_time >= 300:  # 300 seconds = 5 minutes
                    await self.send_periodic_report()
                    self.last_report_time = current_time
                    self.volume_since_last_report = 0.0

                # Execute BUY cycle (all wallets buy tokens with SOL)
                buy_results = await self._execute_buy_cycle()
                
                # Wait a bit between buy and sell
                await asyncio.sleep(5)
                
                # Execute SELL cycle (all wallets sell tokens for SOL)
                sell_results = await self._execute_sell_cycle()
                
                # Notify cycle completion
                await self._notify_cycle_status(cycle)
                
                cycle += 1
                
                delay = random.randint(*self.delays[self.strategy])
                logger.info(f"Session {self.session_id}: Cycle {cycle} completed. Sleeping {delay}s")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Session {self.session_id}: Error in trading loop: {e}")
                await asyncio.sleep(10)
    
    async def _check_sufficient_capital(self) -> bool:
        """Check if at least 50% of wallets have sufficient capital to continue trading."""
        active_wallets = 0
        for wallet in self.wallets:
            pubkey_str = str(wallet.pubkey())
            sol_balance = utils.get_balance(pubkey_str)
            if sol_balance >= self.min_sol_trade:
                active_wallets += 1
        
        # Need at least 50% of wallets to be active
        threshold = len(self.wallets) / 2
        can_continue = active_wallets > threshold
        
        logger.info(f"Session {self.session_id}: Capital check - {active_wallets}/{len(self.wallets)} wallets active (threshold: {threshold})")
        return can_continue
    
    async def _execute_buy_cycle(self):
        """Execute BUY trades for all wallets in parallel."""
        tasks = []
        for client in self.clients:
            tasks.append(self.execute_trade(client, SOL_MINT, self.token_ca))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        logger.info(f"Session {self.session_id}: BUY cycle - {successful}/{len(self.clients)} successful")
        return results
    
    async def _execute_sell_cycle(self):
        """Execute SELL trades for all wallets in parallel."""
        tasks = []
        for client in self.clients:
            tasks.append(self.execute_trade(client, self.token_ca, SOL_MINT))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        logger.info(f"Session {self.session_id}: SELL cycle - {successful}/{len(self.clients)} successful")
        return results
    
    async def _notify_cycle_status(self, cycle: int):
        """Send cycle status update."""
        if self.notification_callback:
            msg = (
                f"📈 **Cycle #{cycle} Completed**\n\n"
                f"🚀 **Total Volume:** ${self.session_volume_usd:,.2f} USD\n"
                f"🔄 **Total Trades:** {self.trade_count}\n\n"
                f"✅ Bot running smoothly!"
            )
            try:
                await self.notification_callback(msg)
            except Exception as e:
                logger.error(f"Failed to send cycle status: {e}")

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
                
                # Use SOL price from config
                trade_value_usd = sol_amount * self.sol_price_usd
                
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
