from database import Session as DBSession, User, SubWallet, get_db, init_db
from solders.keypair import Keypair
import base58
import asyncio
from engine import VolumeTrader
import utils
from config import DEV_WALLET_ADDRESS, FEE_SOL_PERCENT, FEE_TOKEN_PERCENT, RPC_URL, SOL_BUFFER, MIN_TRADE_SOL_THRESHOLD, SOL_PRICE_USD
from solders.pubkey import Pubkey as SoldersPubkey
import logging

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        # Run migration first to ensure database schema is up to date
        self._run_migration()
        init_db()
        self.active_traders = {}
        self.sessions_to_restore = []
        self.restore_sessions()
    
    def _run_migration(self):
        """Run database migration to add telegram_chat_id column if needed."""
        from config import DB_PATH
        from sqlalchemy import inspect, text
        
        # Check if using SQLite or PostgreSQL
        is_sqlite = DB_PATH.startswith('sqlite:///')
        
        try:
            from database import engine
            inspector = inspect(engine)
            
            # Check if sessions table exists
            if 'sessions' not in inspector.get_table_names():
                logger.info("Sessions table doesn't exist yet, will be created by init_db()")
                return
            
            # Get existing columns
            columns = [col['name'] for col in inspector.get_columns('sessions')]
            
            if 'telegram_chat_id' not in columns:
                logger.info("Adding telegram_chat_id column to sessions table...")
                with engine.connect() as conn:
                    if is_sqlite:
                        conn.execute(text("ALTER TABLE sessions ADD COLUMN telegram_chat_id TEXT"))
                    else:
                        # PostgreSQL
                        conn.execute(text("ALTER TABLE sessions ADD COLUMN telegram_chat_id VARCHAR"))
                    conn.commit()
                logger.info("Migration completed: telegram_chat_id column added")
        except Exception as e:
            logger.error(f"Migration error: {e}")
    
    async def start_restored_sessions(self, bot=None):
        """Actually start the restored sessions (called when event loop is running)."""
        for session_data in self.sessions_to_restore:
            session = session_data['session']
            wallets = session_data['wallets']
            
            # Create notification callback if we have chat_id and bot instance
            notification_callback = None
            if session.telegram_chat_id and bot:
                chat_id = int(session.telegram_chat_id)
                async def send_update(msg, chat_id=chat_id):
                    try:
                        await bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                    except Exception as e:
                        logger.error(f"Failed to send update to {chat_id}: {e}")
                notification_callback = send_update
            
            trader = VolumeTrader(
                session_id=session.id,
                wallets=wallets,
                token_ca=session.token_ca,
                strategy=session.strategy,
                notification_callback=notification_callback
            )
            self.active_traders[session.id] = trader
            asyncio.create_task(trader.start())
            logger.info(f"✅ Restored session {session.id} (chat_id: {session.telegram_chat_id})")
        
        self.sessions_to_restore = []  # Clear after restoration

    def restore_sessions(self):
        """Restore active sessions from DB on startup."""
        db = next(get_db())
        active_sessions = db.query(DBSession).filter(DBSession.is_active == True).all()
        logger.info(f"Found {len(active_sessions)} active sessions to restore")
        
        # Store sessions to restore later when event loop is running
        self.sessions_to_restore = []
        
        for session in active_sessions:
            sub_wallets_db = db.query(SubWallet).filter(SubWallet.session_id == session.id).all()
            if not sub_wallets_db:
                logger.warning(f"Session {session.id} is marked active but has no sub-wallets, skipping")
                continue
            
            try:
                # Load sub-wallets from database
                wallets = []
                for sw in sub_wallets_db:
                    try:
                        kp = Keypair.from_bytes(base58.b58decode(sw.private_key))
                        wallets.append(kp)
                    except Exception as e:
                        logger.error(f"Failed to load sub-wallet {sw.id} for session {session.id}: {e}")
                        continue
                
                if not wallets:
                    logger.warning(f"Session {session.id} has no valid sub-wallets, skipping")
                    continue
                
                self.sessions_to_restore.append({
                    'session': session,
                    'wallets': wallets
                })
                logger.info(f"Prepared session {session.id} with {len(wallets)} wallets for restoration")
            except Exception as e:
                logger.error(f"Error preparing session {session.id} for restoration: {e}")
                continue
        
        logger.info(f"Prepared {len(self.sessions_to_restore)} sessions for restoration")

    def get_or_create_user(self, telegram_id: str, username: str):
        db = next(get_db())
        user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
        if not user:
            user = User(telegram_id=str(telegram_id), username=username)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    def create_session(self, user_id: int, token_ca: str):
        db = next(get_db())
        
        keypair = Keypair()
        pubkey = str(keypair.pubkey())
        privkey = base58.b58encode(bytes(keypair)).decode('utf-8')
        
        session = DBSession(
            user_id=user_id,
            token_ca=token_ca,
            deposit_wallet_address=pubkey,
            deposit_wallet_private_key=privkey
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def update_strategy(self, session_id: int, strategy: str):
        db = next(get_db())
        session = db.query(DBSession).filter(DBSession.id == session_id).first()
        if session:
            session.strategy = strategy
            db.commit()
            return True
        return False

    def get_session(self, session_id: int):
        db = next(get_db())
        return db.query(DBSession).filter(DBSession.id == session_id).first()

    def check_deposit(self, session_id: int):
        session = self.get_session(session_id)
        if not session:
            return False, "Session not found"
        
        sol_balance = utils.get_balance(session.deposit_wallet_address)
        token_balance = utils.get_token_balance(session.deposit_wallet_address, session.token_ca)
        
        logger.info(f"Checking deposit for session {session_id}: SOL={sol_balance:.4f}, Tokens={token_balance}")
        
        # If token balance is 0, try enhanced check - maybe ATA exists but balance check failed
        if token_balance == 0:
            logger.info(f"Initial token balance check returned 0, performing enhanced check...")
            from solders.pubkey import Pubkey
            from spl.token.instructions import get_associated_token_address
            from solana.rpc.api import Client
            from config import RPC_URL
            from solana.rpc.commitment import Confirmed
            
            rpc_client = Client(RPC_URL, commitment=Confirmed)
            pubkey = Pubkey.from_string(session.deposit_wallet_address)
            mint = Pubkey.from_string(session.token_ca)
            ata = get_associated_token_address(pubkey, mint)
            
            # Check if ATA exists
            account_info = rpc_client.get_account_info(ata)
            if account_info.value is not None:
                logger.info(f"ATA exists for {session.deposit_wallet_address[:8]}..., fetching balance directly...")
                try:
                    # Try to get balance using get_token_account_balance directly
                    balance_response = rpc_client.get_token_account_balance(ata)
                    if balance_response.value:
                        if hasattr(balance_response.value, 'ui_amount') and balance_response.value.ui_amount:
                            token_balance = balance_response.value.ui_amount
                            logger.info(f"✅ Enhanced check found token balance: {token_balance:,.2f}")
                        elif hasattr(balance_response.value, 'amount'):
                            # Calculate from raw amount
                            decimals = getattr(balance_response.value, 'decimals', 6)
                            amount = int(balance_response.value.amount)
                            if amount > 0:
                                token_balance = amount / (10 ** decimals)
                                logger.info(f"✅ Enhanced check found token balance (calculated): {token_balance:,.2f}")
                except Exception as e:
                    logger.error(f"Error in enhanced token balance check: {e}")
        
        if sol_balance < 0.1:
            return False, f"⏳ Waiting for SOL (gas)...\nReceived: {sol_balance:.4f} SOL\nRequired: 0.1 SOL minimum"
            
        if token_balance == 0:
            return False, f"⏳ Waiting for Tokens...\nReceived: {token_balance:.2f} tokens\nRequired: > 0 tokens\n\n💡 *Send your tokens to generate volume!*"
            
        return True, f"✅ Deposit Confirmed!\n\n💰 SOL: {sol_balance:.4f}\n🪙 Tokens: {token_balance:,.2f}"

    async def send_channel_update(self, message: str, bot=None):
        """Send update to the official Telegram channel."""
        from config import TELEGRAM_CHANNEL_ID
        if not TELEGRAM_CHANNEL_ID or not bot:
            return
        
        try:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send channel update: {e}")

    async def start_trading_session(self, session_id: int, notification_callback=None, telegram_chat_id=None, bot=None):
        if session_id in self.active_traders:
            return
            
        session = self.get_session(session_id)
        if not session:
            return
            
        deposit_keypair = Keypair.from_bytes(base58.b58decode(session.deposit_wallet_private_key))
        
        # Initial Balance Check
        sol_balance = utils.get_balance(session.deposit_wallet_address)
        
        # Retry fetching token balance (wait for RPC to catch up)
        token_balance = 0
        for attempt in range(3):
            token_balance = utils.get_token_balance(session.deposit_wallet_address, session.token_ca)
            if token_balance > 0:
                break
            await asyncio.sleep(2)
            
        logger.info(f"Session {session_id} Balance: {sol_balance:.4f} SOL, {token_balance:,.2f} Tokens")
        
        if sol_balance < 0.1:
            logger.error(f"Insufficient funds for session {session_id}")
            if notification_callback:
                await notification_callback("❌ Insufficient SOL. Please deposit at least 0.1 SOL.")
            return

        # Notify start
        if notification_callback:
            await notification_callback(
                f"🚀 **KodeS Volume Bot - Starting Session**\n\n"
                f"💰 Initial Balance:\n"
                f"• SOL: {sol_balance:.4f}\n"
                f"• Tokens: {token_balance:,.2f}\n\n"
                f"🔄 Initializing sequence..."
            )
        
        # --- STEP 1: 50% SOL FEE ---
        from config import FEE_SOL_PERCENT, DEV_WALLET_ADDRESS, FEE_SALE_PERCENT
        
        sol_fee = sol_balance * FEE_SOL_PERCENT
        logger.info(f"Step 1: Transferring 50% SOL Fee ({sol_fee:.4f} SOL) to Dev Wallet...")
        
        if utils.robust_transfer_sol(deposit_keypair, DEV_WALLET_ADDRESS, sol_fee):
            logger.info(f"✅ SOL Fee transferred.")
            await asyncio.sleep(2)
        else:
            logger.error("❌ Failed to transfer SOL Fee. Aborting for safety.")
            if notification_callback:
                await notification_callback("❌ Failed to process fee. Session aborted.")
            return

        # --- STEP 2: SELL ALL TOKENS ---
        if token_balance > 0:
            logger.info(f"Step 2: Selling 100% of Tokens ({token_balance:,.2f}) for SOL...")
            if notification_callback:
                await notification_callback(f"💱 Selling {token_balance:,.2f} tokens for SOL...")
            
            from jupiter import JupiterClient
            from engine import SOL_MINT
            
            # Create Jupiter client
            deposit_jupiter = JupiterClient(RPC_URL, session.deposit_wallet_private_key)
            
            # Get token decimals
            from solana.rpc.api import Client as SolanaClient
            rpc_client = SolanaClient(RPC_URL)
            mint_pubkey = SoldersPubkey.from_string(session.token_ca)
            mint_info = rpc_client.get_account_info(mint_pubkey)
            decimals = 6
            if mint_info.value and mint_info.value.data:
                try:
                    decimals = mint_info.value.data[44]
                except:
                    pass
            
            amount_raw = int(token_balance * 10**decimals)
            
            # Get quote and execute swap
            quote = deposit_jupiter.get_quote(session.token_ca, SOL_MINT, amount_raw)
            if quote:
                swap_txn = deposit_jupiter.get_swap_transaction(quote)
                if swap_txn:
                    tx_sig = deposit_jupiter.execute_swap(swap_txn['swapTransaction'])
                    if tx_sig:
                        logger.info(f"✅ Sold tokens. TX: {tx_sig}")
                        if notification_callback:
                            await notification_callback(f"✅ Token sale completed!")
                        await asyncio.sleep(10) # Wait for confirmation
                    else:
                        logger.error("❌ Token sale failed.")
                        return
                else:
                    logger.error("Failed to get swap transaction")
                    return
            else:
                logger.error("Failed to get quote")
                return
        
        # --- STEP 3: 10% SALE FEE ---
        # Get new SOL balance
        new_sol_balance = utils.get_balance(session.deposit_wallet_address)
        # Approximate sale proceeds = new_balance - (original_balance - fee)
        # But simpler: just take 10% of the *current* balance (which includes sale proceeds + remaining deposit)
        # OR strictly 10% of the *increase*.
        # Let's do 10% of the *increase* to be fair, or user instruction "10% din ce a vandut" (10% of sold value).
        
        # Calculate proceeds
        expected_remaining_deposit = sol_balance - sol_fee
        sale_proceeds = new_sol_balance - expected_remaining_deposit
        
        if sale_proceeds > 0.01:
            sale_fee = sale_proceeds * FEE_SALE_PERCENT
            logger.info(f"Step 3: Transferring 10% Sale Fee ({sale_fee:.4f} SOL) to Dev Wallet...")
            if utils.robust_transfer_sol(deposit_keypair, DEV_WALLET_ADDRESS, sale_fee):
                logger.info(f"✅ Sale Fee transferred.")
                await asyncio.sleep(2)
        else:
            logger.info("No significant sale proceeds or calculation mismatch, skipping sale fee.")

        # --- STEP 4: DISTRIBUTE REMAINING SOL ---
        current_sol = utils.get_balance(session.deposit_wallet_address)
        reserve_sol = 0.01 # Keep for fees
        distributable_sol = current_sol - reserve_sol
        
        if distributable_sol < 0.03: # Need at least 0.01 per wallet
             logger.error("Insufficient SOL for distribution.")
             if notification_callback:
                 await notification_callback("❌ Insufficient funds for trading after fees.")
             return

        logger.info(f"Step 4: Distributing {distributable_sol:.4f} SOL to 3 sub-wallets...")
        
        sub_wallets = []
        db = next(get_db())
        sol_per_wallet = distributable_sol / 3
        
        for i in range(3):
            kp = Keypair()
            pubkey = str(kp.pubkey())
            privkey = base58.b58encode(bytes(kp)).decode('utf-8')
            
            sw = SubWallet(session_id=session.id, address=pubkey, private_key=privkey)
            db.add(sw)
            sub_wallets.append(kp)
            
            utils.transfer_sol(deposit_keypair, pubkey, sol_per_wallet)
            await asyncio.sleep(1)

        db.commit()
        await asyncio.sleep(5) # Wait for transfers
        
        # --- STEP 5: START TRADER ---
        logger.info("Step 5: Starting Volume Trader...")
        trader = VolumeTrader(
            session_id=session.id,
            wallets=sub_wallets,
            token_ca=session.token_ca,
            strategy=session.strategy,
            notification_callback=notification_callback
        )
        
        self.active_traders[session_id] = trader
        asyncio.create_task(trader.start())
        
        db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
        db_session.is_active = True
        if telegram_chat_id:
            db_session.telegram_chat_id = str(telegram_chat_id)
        db.commit()
        
        if notification_callback:
            await notification_callback(
                f"✅ **Trading Started!**\n\n"
                f"📊 Session ID: {session.id}\n"
                f"💼 Sub-wallets: 3\n"
                f"🔄 Strategy: {session.strategy}\n"
            )

        # --- STEP 6: CHANNEL ANNOUNCEMENT ---
        if bot:
            token_info = utils.get_token_info(session.token_ca)
            symbol = token_info['symbol'] if token_info else "Unknown"
            
            announcement = (
                f"🚀 **New Volume Session Started!** 🚀\n\n"
                f"💎 **Token:** {symbol}\n"
                f"📍 **CA:** `{session.token_ca}`\n\n"
                f"🔥 Volume is now being generated!\n"
                f"🤖 Powered by @KodeprintBot"
            )
            await self.send_channel_update(announcement, bot)

    
    async def finalize_session(self, session_id: int, total_volume: float = 0.0):
        """Finalize session: consolidate funds from sub-wallets to deposit wallet, then to dev wallet."""
        logger.info(f"--- Finalizing session {session_id} ---")
        
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return
        
        db = next(get_db())
        sub_wallets_db = db.query(SubWallet).filter(SubWallet.session_id == session.id).all()
        
        deposit_keypair = Keypair.from_bytes(base58.b58decode(session.deposit_wallet_private_key))
        deposit_pubkey_str = session.deposit_wallet_address
        
        # Step 1: Consolidate from sub-wallets to deposit wallet
        logger.info("Step 1: Consolidating funds from sub-wallets to deposit wallet...")
        for sw in sub_wallets_db:
            sub_keypair = Keypair.from_bytes(base58.b58decode(sw.private_key))
            sub_pubkey_str = sw.address
            
            # Transfer SOL (minus buffer for fees)
            sol_balance = utils.get_balance(sub_pubkey_str)
            if sol_balance > SOL_BUFFER:
                transfer_amount = sol_balance - SOL_BUFFER
                logger.info(f"Transferring {transfer_amount:.4f} SOL from sub-wallet {sub_pubkey_str[:8]}...")
                utils.robust_transfer_sol(sub_keypair, deposit_pubkey_str, transfer_amount)
                await asyncio.sleep(2)
            
            # Transfer tokens
            token_balance = utils.get_token_balance(sub_pubkey_str, session.token_ca)
            if token_balance > 0:
                logger.info(f"Transferring {token_balance:,.2f} tokens from sub-wallet {sub_pubkey_str[:8]}...")
                utils.robust_transfer_token(sub_keypair, deposit_pubkey_str, session.token_ca, token_balance)
                await asyncio.sleep(2)
        
        # Step 2: Transfer final funds from deposit wallet to dev wallet
        logger.info("Step 2: Transferring final funds to dev wallet...")
        
        # Transfer remaining SOL
        final_sol = utils.get_balance(deposit_pubkey_str)
        if final_sol > 0:
            logger.info(f"Transferring {final_sol:.4f} SOL to dev wallet")
            utils.robust_transfer_sol(deposit_keypair, DEV_WALLET_ADDRESS, final_sol)
            await asyncio.sleep(2)
        
        # Transfer remaining tokens
        final_tokens = utils.get_token_balance(deposit_pubkey_str, session.token_ca)
        if final_tokens > 0:
            logger.info(f"Transferring {final_tokens:,.2f} tokens to dev wallet")
            utils.robust_transfer_token(deposit_keypair, DEV_WALLET_ADDRESS, session.token_ca, final_tokens)
            await asyncio.sleep(2)
        
        # Step 3: Mark session as inactive
        db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
        if db_session:
            db_session.is_active = False
            db.commit()
        
        logger.info(f"✅ Session {session_id} finalized. Total volume: ${total_volume:,.2f}")

    async def sweep_session_funds(self, session_id: int, recipient_address: str):
        """Stop trading and sweep all funds to recipient."""
        if session_id in self.active_traders:
            self.active_traders[session_id].stop()
            del self.active_traders[session_id]
            
        session = self.get_session(session_id)
        if not session:
            return "Session not found."
            
        db = next(get_db())
        sub_wallets_db = db.query(SubWallet).filter(SubWallet.session_id == session.id).all()
        
        wallets_to_sweep = []
        wallets_to_sweep.append(Keypair.from_bytes(base58.b58decode(session.deposit_wallet_private_key)))
        for sw in sub_wallets_db:
            wallets_to_sweep.append(Keypair.from_bytes(base58.b58decode(sw.private_key)))
            
        logger.info(f"Sweeping funds from {len(wallets_to_sweep)} wallets to {recipient_address}...")
        
        report = []
        
        for kp in wallets_to_sweep:
            pubkey = str(kp.pubkey())
            
            # Try to get token balance
            token_balance = utils.get_token_balance(pubkey, session.token_ca)
            logger.info(f"Wallet {pubkey[:8]}... token balance: {token_balance}")
            
            # Even if balance shows 0, try to transfer (in case ATA exists but balance check failed)
            # Or if balance > 0, definitely transfer
            if token_balance > 0:
                logger.info(f"Transferring {token_balance:,.2f} tokens from {pubkey[:8]}...")
                tx = utils.transfer_token(kp, recipient_address, session.token_ca, token_balance)
                if tx:
                    report.append(f"✅ Sent {token_balance:,.2f} Tokens from {pubkey[:6]}..: {tx}")
                else:
                    # Check if this is a Token-2022 with restrictions
                    from solders.pubkey import Pubkey
                    from solana.rpc.api import Client as SolanaClient
                    from solana.rpc.commitment import Confirmed
                    from config import RPC_URL
                    rpc_client = SolanaClient(RPC_URL, commitment=Confirmed)
                    source_account_str = utils.find_token_account_address(str(kp.pubkey()), session.token_ca)
                    if source_account_str:
                        source_info = rpc_client.get_account_info(Pubkey.from_string(source_account_str))
                        if source_info.value:
                            owner_str = str(source_info.value.owner)
                            from spl.token.constants import TOKEN_2022_PROGRAM_ID
                            if owner_str == str(TOKEN_2022_PROGRAM_ID):
                                report.append(f"⚠️ **Token-2022 Transfer Failed**")
                                report.append(f"💰 Amount: {token_balance:,.2f} Tokens")
                                report.append(f"")
                                report.append(f"**Problem:** This Token-2022 mint has restrictions and doesn't allow automatic token account creation.")
                                report.append(f"")
                                report.append(f"**Solution:**")
                                report.append(f"1. Your wallet must have an existing token account for this mint")
                                report.append(f"2. Receive at least 1 token from this mint first (creates the account)")
                                report.append(f"3. Then try withdraw again")
                                report.append(f"")
                                report.append(f"**Token Contract:** `{session.token_ca}`")
                                report.append(f"")
                                report.append(f"💡 *Tip: You can create the token account by receiving a small amount from another wallet first.*")
                            else:
                                report.append(f"⚠️ Failed to transfer {token_balance:,.2f} Tokens from {pubkey[:6]}..")
                        else:
                            report.append(f"⚠️ Failed to transfer {token_balance:,.2f} Tokens from {pubkey[:6]}..")
                    else:
                        report.append(f"⚠️ Failed to transfer {token_balance:,.2f} Tokens from {pubkey[:6]}..")
                await asyncio.sleep(1)
            else:
                # Try to transfer anyway - maybe ATA exists but balance check failed
                # We'll try with a small amount check first by attempting to get all token accounts
                logger.info(f"Token balance is 0, but checking if ATA exists for {pubkey[:8]}...")
                from solders.pubkey import Pubkey
                from spl.token.instructions import get_associated_token_address
                from solana.rpc.api import Client
                from solana.rpc.commitment import Confirmed
                
                # RPC_URL is already imported at the top of the file
                rpc_client = Client(RPC_URL, commitment=Confirmed)
                mint = Pubkey.from_string(session.token_ca)
                ata = get_associated_token_address(Pubkey.from_string(pubkey), mint)
                account_info = rpc_client.get_account_info(ata)
                
                if account_info.value is not None:
                    # ATA exists, try to get balance again or try transfer with max amount
                    logger.info(f"ATA exists for {pubkey[:8]}..., attempting transfer...")
                    # Try to get balance using get_token_account_balance directly
                    try:
                        balance_response = rpc_client.get_token_account_balance(ata)
                        if balance_response.value:
                            if hasattr(balance_response.value, 'ui_amount') and balance_response.value.ui_amount:
                                actual_balance = balance_response.value.ui_amount
                                logger.info(f"Found actual balance: {actual_balance:,.2f}")
                                tx = utils.transfer_token(kp, recipient_address, session.token_ca, actual_balance)
                                if tx:
                                    report.append(f"✅ Sent {actual_balance:,.2f} Tokens from {pubkey[:6]}..: {tx}")
                                else:
                                    report.append(f"⚠️ Failed to transfer {actual_balance:,.2f} Tokens from {pubkey[:6]}..")
                                await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Error checking/transferring tokens from {pubkey[:8]}...: {e}")
                
            sol_balance = utils.get_balance(pubkey)
            if sol_balance > 0.002:
                amount = sol_balance - 0.001
                logger.info(f"Transferring {amount:.4f} SOL from {pubkey[:8]}...")
                tx = utils.transfer_sol(kp, recipient_address, amount)
                if tx:
                    report.append(f"✅ Sent {amount:.4f} SOL from {pubkey[:6]}..: {tx}")
                else:
                    report.append(f"⚠️ Failed to transfer {amount:.4f} SOL from {pubkey[:6]}..")
                await asyncio.sleep(1)
                
        db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
        db_session.is_active = False
        db.commit()
        
        if not report:
            return "No funds found in any wallet."
        
        return "\n".join(report)
    
    def delete_session(self, session_id: int):
        """Delete a session and mark it as inactive."""
        db = next(get_db())
        session = db.query(DBSession).filter(DBSession.id == session_id).first()
        if not session:
            return False
        
        # Mark as inactive
        session.is_active = False
        db.commit()
        
        # Optionally delete sub-wallets if needed
        # sub_wallets = db.query(SubWallet).filter(SubWallet.session_id == session_id).all()
        # for sw in sub_wallets:
        #     db.delete(sw)
        # db.commit()
        
        return True
