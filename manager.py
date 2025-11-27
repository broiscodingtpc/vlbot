from database import Session as DBSession, User, SubWallet, get_db, init_db
from solders.keypair import Keypair
import base58
import asyncio
from engine import VolumeTrader
import utils
from config import DEV_WALLET_ADDRESS, FEE_SOL_PERCENT, FEE_TOKEN_PERCENT
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

    async def start_trading_session(self, session_id: int, notification_callback=None, telegram_chat_id=None):
        if session_id in self.active_traders:
            return
            
        session = self.get_session(session_id)
        if not session:
            return
            
        deposit_keypair = Keypair.from_bytes(base58.b58decode(session.deposit_wallet_private_key))
        
        sol_balance = utils.get_balance(session.deposit_wallet_address)
        
        # Retry fetching token balance (wait for RPC to catch up) with enhanced check
        token_balance = 0
        for attempt in range(3):
            token_balance = utils.get_token_balance(session.deposit_wallet_address, session.token_ca)
            if token_balance > 0:
                break
            
            # Enhanced check if initial check returned 0
            if token_balance == 0:
                logger.info(f"Attempt {attempt + 1}/3: Initial check returned 0, trying enhanced check...")
                from solders.pubkey import Pubkey
                from spl.token.instructions import get_associated_token_address
                from solana.rpc.api import Client
                from config import RPC_URL
                from solana.rpc.commitment import Confirmed
                
                rpc_client = Client(RPC_URL, commitment=Confirmed)
                pubkey = Pubkey.from_string(session.deposit_wallet_address)
                mint = Pubkey.from_string(session.token_ca)
                ata = get_associated_token_address(pubkey, mint)
                
                account_info = rpc_client.get_account_info(ata)
                if account_info.value is not None:
                    try:
                        balance_response = rpc_client.get_token_account_balance(ata)
                        if balance_response.value:
                            if hasattr(balance_response.value, 'ui_amount') and balance_response.value.ui_amount:
                                token_balance = balance_response.value.ui_amount
                                logger.info(f"✅ Enhanced check found balance: {token_balance:,.2f}")
                                break
                            elif hasattr(balance_response.value, 'amount'):
                                decimals = getattr(balance_response.value, 'decimals', 6)
                                amount = int(balance_response.value.amount)
                                if amount > 0:
                                    token_balance = amount / (10 ** decimals)
                                    logger.info(f"✅ Enhanced check found balance (calculated): {token_balance:,.2f}")
                                    break
                    except Exception as e:
                        logger.error(f"Error in enhanced check: {e}")
            
            await asyncio.sleep(2)
            
        logger.info(f"Session {session_id} Balance: {sol_balance:.4f} SOL, {token_balance:,.2f} Tokens")
        
        if sol_balance < 0.1:
            logger.error(f"Insufficient funds for session {session_id}")
            return

        # Collect 50% SOL fee
        fee_sol = sol_balance * FEE_SOL_PERCENT
        logger.info(f"Collecting {fee_sol} SOL fee to dev")
        utils.transfer_sol(deposit_keypair, DEV_WALLET_ADDRESS, fee_sol)
        await asyncio.sleep(1)
        
        # Collect 50% Token fee
        if token_balance > 0:
            fee_token = token_balance * FEE_TOKEN_PERCENT
            logger.info(f"Collecting {fee_token} tokens fee to dev")
            utils.transfer_token(deposit_keypair, DEV_WALLET_ADDRESS, session.token_ca, fee_token)
            await asyncio.sleep(1)
        
        # Generate 3 sub-wallets
        sub_wallets = []
        db = next(get_db())
        
        remaining_sol = sol_balance - fee_sol
        remaining_tokens = token_balance - (fee_token if token_balance > 0 else 0)
        
        # Each wallet gets: minimal SOL for gas + equal share of tokens
        # After fee: 0.1 SOL -> 0.05 SOL remaining
        # Distribute: 3 wallets * 0.01 SOL = 0.03 SOL, keep 0.02 SOL in deposit wallet
        # This gives each wallet enough for ~5 trades (0.01 SOL / 0.002 SOL per trade)
        gas_per_wallet = 0.01  # Enough for multiple trades (each trade needs ~0.002 SOL fees)
        tokens_per_wallet = remaining_tokens / 3 if remaining_tokens > 0 else 0
        
        # Verify we have enough SOL to distribute
        total_sol_needed = gas_per_wallet * 3
        if remaining_sol < total_sol_needed:
            logger.warning(f"Not enough SOL to distribute: have {remaining_sol:.4f}, need {total_sol_needed:.4f}")
            # Reduce gas per wallet proportionally
            gas_per_wallet = remaining_sol / 3
            logger.info(f"Reduced gas_per_wallet to {gas_per_wallet:.4f}")
        
        for _ in range(3):
            kp = Keypair()
            pubkey = str(kp.pubkey())
            privkey = base58.b58encode(bytes(kp)).decode('utf-8')
            
            sw = SubWallet(session_id=session.id, address=pubkey, private_key=privkey)
            db.add(sw)
            sub_wallets.append(kp)
            
            # Give minimal SOL for gas
            if gas_per_wallet > 0:
                result = utils.transfer_sol(deposit_keypair, pubkey, gas_per_wallet)
                logger.info(f"Transferred {gas_per_wallet} SOL to {pubkey[:8]}: {result}")
                await asyncio.sleep(1)
                
            # Give tokens
            if tokens_per_wallet > 0:
                logger.info(f"Attempting to transfer {tokens_per_wallet:,.2f} tokens to {pubkey[:8]}...")
                result = utils.transfer_token(deposit_keypair, pubkey, session.token_ca, tokens_per_wallet)
                if result:
                    logger.info(f"✅ Transferred {tokens_per_wallet:,.2f} tokens to {pubkey[:8]}: {result}")
                else:
                    logger.error(f"❌ Failed to transfer {tokens_per_wallet:,.2f} tokens to {pubkey[:8]}")
                await asyncio.sleep(2)  # Give more time for confirmation

        db.commit()
        
        # Wait for transfers to confirm on blockchain and verify
        logger.info("Waiting for transfers to confirm on blockchain...")
        await asyncio.sleep(5)
        
        # Verify tokens arrived in at least one sub-wallet
        max_retries = 5
        for attempt in range(max_retries):
            tokens_found = False
            for kp in sub_wallets:
                balance = utils.get_token_balance(str(kp.pubkey()), session.token_ca)
                if balance > 0:
                    logger.info(f"Verified {balance} tokens in wallet {str(kp.pubkey())[:8]}")
                    tokens_found = True
                    break
            
            if tokens_found:
                break
            else:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Tokens not yet visible, waiting 3s...")
                await asyncio.sleep(3)
        
        if not tokens_found:
            logger.warning(f"Could not verify token transfers for session {session.id}")
            logger.warning("Tokens may still be in deposit wallet. Checking...")
            # Check if tokens are still in deposit wallet
            deposit_token_balance = utils.get_token_balance(session.deposit_wallet_address, session.token_ca)
            if deposit_token_balance > 0:
                logger.info(f"✅ Found {deposit_token_balance:,.2f} tokens still in deposit wallet. Will use deposit wallet for trading.")
                # Use deposit wallet as the only trading wallet if sub-wallets don't have tokens
                sub_wallets = [deposit_keypair]  # Use deposit wallet instead
                logger.warning("Using deposit wallet for trading since sub-wallets don't have tokens")
            else:
                logger.error(f"❌ No tokens found in deposit wallet or sub-wallets. Cannot start trading.")
                # Mark session as inactive but don't delete it - allow user to withdraw
                db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
                if db_session:
                    db_session.is_active = False
                    db.commit()
                return
            
        
        logger.info(f"Creating VolumeTrader for session {session.id} with {len(sub_wallets)} wallets")
        trader = VolumeTrader(
            session_id=session.id,
            wallets=sub_wallets,
            token_ca=session.token_ca,
            strategy=session.strategy,
            notification_callback=notification_callback
        )
        
        logger.info(f"Starting trader task for session {session.id}")
        task = asyncio.create_task(trader.start())
        self.active_traders[session_id] = trader
        
        db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
        db_session.is_active = True
        if telegram_chat_id:
            db_session.telegram_chat_id = str(telegram_chat_id)
        db.commit()
        logger.info(f"Session {session.id} marked as active in DB (chat_id: {telegram_chat_id})")

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
                    report.append(f"⚠️ Failed to transfer {token_balance:,.2f} Tokens from {pubkey[:6]}..")
                await asyncio.sleep(1)
            else:
                # Try to transfer anyway - maybe ATA exists but balance check failed
                # We'll try with a small amount check first by attempting to get all token accounts
                logger.info(f"Token balance is 0, but checking if ATA exists for {pubkey[:8]}...")
                from solders.pubkey import Pubkey
                from spl.token.instructions import get_associated_token_address
                from solana.rpc.api import Client
                from config import RPC_URL
                from solana.rpc.commitment import Confirmed
                
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
