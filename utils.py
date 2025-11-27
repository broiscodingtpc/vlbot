from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.system_program import TransferParams as SolTransferParams, transfer as sol_transfer
from solders.transaction import Transaction
from spl.token.instructions import transfer_checked, TransferCheckedParams, transfer, TransferParams, get_associated_token_address, create_associated_token_account
from spl.token.constants import TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID
from config import RPC_URL
import requests
import logging

logger = logging.getLogger(__name__)
client = Client(RPC_URL, commitment=Confirmed)

def get_balance(pubkey_str: str) -> float:
    """Get SOL balance in lamports converted to SOL."""
    try:
        pubkey = Pubkey.from_string(pubkey_str)
        response = client.get_balance(pubkey)
        return response.value / 10**9
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0.0

def get_token_balance(pubkey_str: str, mint_str: str) -> float:
    """Get SPL Token balance - checks both ATA and all token accounts."""
    try:
        pubkey = Pubkey.from_string(pubkey_str)
        mint = Pubkey.from_string(mint_str)
        
        # First try ATA (most common case)
        ata = get_associated_token_address(pubkey, mint)
        logger.info(f"Checking token balance for {pubkey_str[:8]}... | Mint: {mint_str[:8]}... | ATA: {ata}")
        
        account_info = client.get_account_info(ata)
        if account_info.value is not None:
            logger.info(f"ATA exists for {pubkey_str[:8]}..., fetching balance...")
            response = client.get_token_account_balance(ata)
            
            if response.value is not None:
                balance = None
                if hasattr(response.value, 'ui_amount') and response.value.ui_amount is not None:
                    balance = response.value.ui_amount
                    logger.info(f"Token balance (ui_amount): {balance} for {pubkey_str[:8]}...")
                elif hasattr(response.value, 'amount'):
                    decimals = getattr(response.value, 'decimals', 6)
                    amount = int(response.value.amount)
                    if amount > 0:
                        balance = amount / (10 ** decimals)
                        logger.info(f"Token balance (calculated): {balance} for {pubkey_str[:8]}...")
                
                if balance is not None and balance > 0:
                    logger.info(f"✅ Token balance found in ATA: {balance:,.2f}")
                    return float(balance)
        
        # ATA doesn't exist or has 0 balance - check all token accounts
        logger.info(f"ATA check failed, searching all token accounts for {pubkey_str[:8]}...")
        return get_token_balance_from_all_accounts(pubkey_str, mint_str)
        
    except Exception as e:
        logger.error(f"Error getting token balance for {pubkey_str[:8]}... mint {mint_str[:8]}...: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0.0

def get_token_balance_from_all_accounts(pubkey_str: str, mint_str: str) -> float:
    """Get token balance by checking all token accounts owned by the wallet."""
    try:
        pubkey = Pubkey.from_string(pubkey_str)
        mint = Pubkey.from_string(mint_str)
        
        logger.info(f"Searching all token accounts for {pubkey_str[:8]}... with mint {mint_str[:8]}...")
        
        # Method 1: Try get_token_accounts_by_owner (standard Solana RPC)
        try:
            token_accounts = client.get_token_accounts_by_owner(
                pubkey,
                TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
            )
            
            if token_accounts.value:
                logger.info(f"Found {len(token_accounts.value)} token account(s) for {pubkey_str[:8]}...")
                
                # Search through all token accounts to find the one with our mint
                for account_info in token_accounts.value:
                    try:
                        # Parse account data to get mint and balance
                        account_data = account_info.account.data
                        
                        # Token account structure: mint (32 bytes) + owner (32 bytes) + amount (8 bytes) + ...
                        if len(account_data) >= 72:
                            # Extract mint (first 32 bytes)
                            account_mint_bytes = account_data[0:32]
                            account_mint = Pubkey.from_bytes(account_mint_bytes)
                            
                            # Check if this account matches our mint
                            if str(account_mint) == mint_str:
                                # Extract amount (bytes 64-72)
                                amount_bytes = account_data[64:72]
                                amount = int.from_bytes(amount_bytes, byteorder='little')
                                
                                # Get decimals from mint
                                mint_info = client.get_account_info(mint)
                                decimals = 6  # default
                                if mint_info.value and mint_info.value.data:
                                    try:
                                        decimals = mint_info.value.data[44]
                                    except:
                                        pass
                                
                                if amount > 0:
                                    balance = amount / (10 ** decimals)
                                    logger.info(f"✅ Found token balance in token account: {balance:,.2f} for {pubkey_str[:8]}...")
                                    return float(balance)
                    except Exception as e:
                        logger.debug(f"Error parsing token account: {e}")
                        continue
        except Exception as e:
            logger.warning(f"get_token_accounts_by_owner failed: {e}")
        
        # Method 2: Try using Helius getTokenAccounts API (if using Helius RPC)
        if 'helius' in RPC_URL.lower():
            logger.info("Trying Helius getTokenAccounts API...")
            try:
                balance = _get_token_balance_helius_api(pubkey_str, mint_str)
                if balance > 0:
                    return balance
            except Exception as e:
                logger.warning(f"Helius API method failed: {e}")
        
        logger.info(f"No matching token account found for mint {mint_str[:8]}...")
        return 0.0
        
    except Exception as e:
        logger.error(f"Error searching token accounts for {pubkey_str[:8]}...: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0.0

def _get_token_balance_helius_api(pubkey_str: str, mint_str: str) -> float:
    """Get token balance using Helius getTokenAccounts API."""
    import json
    
    # Extract API key from RPC URL if present
    api_key = None
    if 'api-key=' in RPC_URL:
        api_key = RPC_URL.split('api-key=')[1].split('&')[0]
    
    if not api_key:
        return 0.0
    
    helius_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    
    page = 1
    total_balance = 0.0
    
    while True:
        payload = {
            "jsonrpc": "2.0",
            "method": "getTokenAccounts",
            "id": "421",
            "params": {
                "page": page,
                "limit": 1000,
                "mint": mint_str,
            },
        }
        
        response = requests.post(helius_url, json=payload, timeout=10)
        data = response.json()
        
        if not data.get('result') or not data['result'].get('token_accounts') or len(data['result']['token_accounts']) == 0:
            break
        
        # Check each token account to see if owner matches our wallet
        for account in data['result']['token_accounts']:
            if account.get('owner') == pubkey_str:
                # Found matching account
                amount = int(account.get('amount', 0))
                
                # Get decimals
                mint_info = client.get_account_info(Pubkey.from_string(mint_str))
                decimals = 6
                if mint_info.value and mint_info.value.data:
                    try:
                        decimals = mint_info.value.data[44]
                    except:
                        pass
                
                if amount > 0:
                    balance = amount / (10 ** decimals)
                    logger.info(f"✅ Found token balance via Helius API: {balance:,.2f} for {pubkey_str[:8]}...")
                    return float(balance)
        
        page += 1
        if page > 10:  # Safety limit
            break
    
    return 0.0

def transfer_sol(sender_keypair: Keypair, recipient_pubkey_str: str, amount_sol: float):
    """Transfer SOL from sender to recipient."""
    try:
        from solders.message import Message
        from solders.transaction import Transaction as SoldersTransaction
        
        recipient = Pubkey.from_string(recipient_pubkey_str)
        lamports = int(amount_sol * 10**9)
        
        ix = sol_transfer(
            SolTransferParams(
                from_pubkey=sender_keypair.pubkey(),
                to_pubkey=recipient,
                lamports=lamports
            )
        )
        
        # Fetch recent blockhash
        recent_blockhash = client.get_latest_blockhash().value.blockhash
        
        # Create Message
        msg = Message.new_with_blockhash(
            [ix],
            sender_keypair.pubkey(),
            recent_blockhash
        )
        
        # Create and sign Transaction
        txn = SoldersTransaction([sender_keypair], msg, recent_blockhash)
        
        result = client.send_transaction(txn)
        return result.value
    except Exception as e:
        print(f"Transfer SOL failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_token_program_id(mint_str: str) -> Pubkey:
    """Detect the token program ID (TOKEN_PROGRAM_ID or TOKEN_2022_PROGRAM_ID) by checking mint owner."""
    try:
        mint = Pubkey.from_string(mint_str)
        
        # Get mint account info to check owner
        mint_info = client.get_account_info(mint)
        
        if not mint_info.value:
            logger.warning(f"Mint {mint_str[:8]}... not found, defaulting to TOKEN_PROGRAM_ID")
            return TOKEN_PROGRAM_ID
        
        # Get the owner (program ID) of the mint account
        mint_owner = mint_info.value.owner
        
        # Compare with known program IDs
        if str(mint_owner) == str(TOKEN_2022_PROGRAM_ID):
            logger.info(f"Mint {mint_str[:8]}... is Token-2022 (owner: {mint_owner})")
            return TOKEN_2022_PROGRAM_ID
        else:
            logger.info(f"Mint {mint_str[:8]}... is Standard Token (owner: {mint_owner})")
            return TOKEN_PROGRAM_ID
    except Exception as e:
        logger.error(f"Error detecting token program ID for {mint_str[:8]}...: {e}")
        # Default to standard token program
        return TOKEN_PROGRAM_ID

def create_ata_manually(payer_keypair: Keypair, owner_pubkey: Pubkey, mint_pubkey: Pubkey, token_program_id: Pubkey = None) -> bool:
    """Manually create ATA (Associated Token Account) with proper program ID detection."""
    try:
        # Detect token program ID if not provided
        if token_program_id is None:
            token_program_id = get_token_program_id(str(mint_pubkey))
        
        # Get ATA address
        ata_address = get_associated_token_address(owner_pubkey, mint_pubkey)
        
        # Check if ATA already exists
        ata_info = client.get_account_info(ata_address)
        if ata_info.value is not None:
            logger.info(f"ATA already exists: {ata_address}")
            return True
        
        # Create ATA instruction with correct program ID
        create_ata_ix = create_associated_token_account(
            payer=payer_keypair.pubkey(),
            owner=owner_pubkey,
            mint=mint_pubkey,
            token_program_id=token_program_id
        )
        
        # Build and send transaction
        from solders.message import Message
        from solders.transaction import Transaction as SoldersTransaction
        from solana.rpc.commitment import Confirmed
        
        recent_blockhash = client.get_latest_blockhash(commitment=Confirmed).value.blockhash
        msg = Message([create_ata_ix], payer_keypair.pubkey())
        txn = SoldersTransaction([payer_keypair], msg, recent_blockhash)
        
        result = client.send_transaction(txn)
        if result.value:
            logger.info(f"✅ ATA created successfully: {ata_address}")
            return True
        else:
            logger.error(f"Failed to create ATA: {result}")
            return False
    except Exception as e:
        logger.error(f"Error creating ATA manually: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def robust_transfer_sol(sender_keypair: Keypair, recipient_pubkey_str: str, amount_sol: float, max_retries: int = 3) -> bool:
    """Robust SOL transfer with retries."""
    import time
    for attempt in range(max_retries):
        try:
            result = transfer_sol(sender_keypair, recipient_pubkey_str, amount_sol)
            if result:
                logger.info(f"✅ SOL transfer successful: {amount_sol} SOL to {recipient_pubkey_str[:8]}...")
                return True
        except Exception as e:
            logger.warning(f"SOL transfer attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Use time.sleep instead of asyncio.sleep for sync function
    
    logger.error(f"❌ SOL transfer failed after {max_retries} attempts")
    return False

def robust_transfer_token(sender_keypair: Keypair, recipient_pubkey_str: str, mint_str: str, amount_ui: float, max_retries: int = 3) -> bool:
    """Robust token transfer with retries and ATA creation."""
    import time
    # First, ensure recipient has ATA
    try:
        from solders.pubkey import Pubkey
        recipient_pubkey = Pubkey.from_string(recipient_pubkey_str)
        mint_pubkey = Pubkey.from_string(mint_str)
        
        # Try to create ATA if needed
        token_program_id = get_token_program_id(mint_str)
        create_ata_manually(sender_keypair, recipient_pubkey, mint_pubkey, token_program_id)
    except Exception as e:
        logger.warning(f"ATA creation/preparation failed: {e}, continuing with transfer attempt...")
    
    # Attempt transfer with retries
    for attempt in range(max_retries):
        try:
            result = transfer_token(sender_keypair, recipient_pubkey_str, mint_str, amount_ui)
            if result:
                logger.info(f"✅ Token transfer successful: {amount_ui} tokens to {recipient_pubkey_str[:8]}...")
                return True
        except Exception as e:
            logger.warning(f"Token transfer attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Use time.sleep instead of asyncio.sleep for sync function
    
    logger.error(f"❌ Token transfer failed after {max_retries} attempts")
    return False

def find_token_account_address(pubkey_str: str, mint_str: str) -> str:
    """Find the actual token account address for a wallet and mint (ATA or other)."""
    try:
        pubkey = Pubkey.from_string(pubkey_str)
        mint = Pubkey.from_string(mint_str)
        
        # First try ATA
        ata = get_associated_token_address(pubkey, mint)
        account_info = client.get_account_info(ata)
        if account_info.value is not None:
            logger.info(f"Found ATA for {pubkey_str[:8]}...: {ata}")
            return str(ata)
        
        # ATA doesn't exist, search all token accounts
        logger.info(f"ATA not found, searching token accounts for {pubkey_str[:8]}...")
        
        # Try get_token_accounts_by_owner
        try:
            token_accounts = client.get_token_accounts_by_owner(
                pubkey,
                TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
            )
            
            if token_accounts.value:
                for account_info in token_accounts.value:
                    try:
                        account_data = account_info.account.data
                        if len(account_data) >= 72:
                            account_mint_bytes = account_data[0:32]
                            account_mint = Pubkey.from_bytes(account_mint_bytes)
                            
                            if str(account_mint) == mint_str:
                                # Get the token account address (pubkey of the account)
                                account_address = str(account_info.pubkey)
                                logger.info(f"Found token account for {pubkey_str[:8]}...: {account_address}")
                                return account_address
                    except Exception as e:
                        logger.debug(f"Error parsing token account: {e}")
                        continue
        except Exception as e:
            logger.warning(f"get_token_accounts_by_owner failed: {e}")
        
        # Try Helius API if available
        if 'helius' in RPC_URL.lower():
            try:
                account_address = _find_token_account_helius_api(pubkey_str, mint_str)
                if account_address:
                    return account_address
            except Exception as e:
                logger.warning(f"Helius API method failed: {e}")
        
        return None
    except Exception as e:
        logger.error(f"Error finding token account: {e}")
        return None

def _find_token_account_helius_api(pubkey_str: str, mint_str: str) -> str:
    """Find token account address using Helius getTokenAccounts API."""
    import json
    
    api_key = None
    if 'api-key=' in RPC_URL:
        api_key = RPC_URL.split('api-key=')[1].split('&')[0]
    
    if not api_key:
        return None
    
    helius_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    page = 1
    
    while page <= 10:  # Safety limit
        payload = {
            "jsonrpc": "2.0",
            "method": "getTokenAccounts",
            "id": "421",
            "params": {
                "page": page,
                "limit": 1000,
                "mint": mint_str,
            },
        }
        
        response = requests.post(helius_url, json=payload, timeout=10)
        data = response.json()
        
        if not data.get('result') or not data['result'].get('token_accounts'):
            break
        
        for account in data['result']['token_accounts']:
            if account.get('owner') == pubkey_str:
                account_address = account.get('address')
                if account_address:
                    logger.info(f"Found token account via Helius API: {account_address}")
                    return account_address
        
        page += 1
    
    return None

def transfer_token(sender_keypair: Keypair, recipient_pubkey_str: str, mint_str: str, amount_ui: float):
    """Transfer SPL Tokens."""
    try:
        from solders.message import Message
        from solders.transaction import Transaction as SoldersTransaction
        
        recipient = Pubkey.from_string(recipient_pubkey_str)
        mint = Pubkey.from_string(mint_str)
        
        # Find the actual token account (ATA or other)
        source_account_str = find_token_account_address(str(sender_keypair.pubkey()), mint_str)
        if not source_account_str:
            logger.error(f"No token account found for {str(sender_keypair.pubkey())[:8]}... and mint {mint_str[:8]}...")
            return None
        
        source_account = Pubkey.from_string(source_account_str)
        logger.info(f"Using token account {source_account_str[:8]}... for transfer")
        
        # CRITICAL FIX: Detect token program ID from mint owner (not from source account)
        # This ensures we use the correct program ID for both ATA creation and transfer
        token_program_id = get_token_program_id(mint_str)
        is_token_2022 = token_program_id == TOKEN_2022_PROGRAM_ID
        
        if is_token_2022:
            logger.info(f"Detected Token-2022 mint - using TOKEN_2022_PROGRAM_ID")
        else:
            logger.info(f"Detected Standard Token mint - using TOKEN_PROGRAM_ID")
        
        # Verify source account is valid and owned by the correct token program
        source_info = client.get_account_info(source_account)
        if source_info.value is None:
            logger.error(f"Source token account {source_account_str[:8]}... does not exist")
            return None
        
        # Verify it's a token account (check owner matches detected program ID)
        owner_str = str(source_info.value.owner)
        if owner_str != str(token_program_id):
            logger.error(f"Source account {source_account_str[:8]}... owner mismatch: {owner_str} vs {token_program_id}")
            return None
        
        # Use dynamically detected token_program_id for both standard and Token-2022
        destination_ata = get_associated_token_address(recipient, mint)
        logger.info(f"Destination ATA address: {destination_ata}")
        
        instructions = []
        
        # Check if dest ATA exists
        dest_info = client.get_account_info(destination_ata)
        if dest_info.value is None:
            logger.info(f"ATA doesn't exist, checking if recipient has any token account...")
            # First check if recipient has any token account for this mint
            recipient_token_account = find_token_account_address(recipient_pubkey_str, mint_str)
            if recipient_token_account:
                destination_account = Pubkey.from_string(recipient_token_account)
                logger.info(f"Using existing token account: {recipient_token_account[:8]}...")
                instructions = []
            else:
                # Try to create ATA with the correct program ID (detected from mint)
                logger.info(f"Attempting to create ATA for recipient {recipient} with program_id={token_program_id}")
                try:
                    # CRITICAL FIX: Use dynamically detected token_program_id
                    create_ata_ix = create_associated_token_account(
                        payer=sender_keypair.pubkey(),
                        owner=recipient,
                        mint=mint,
                        token_program_id=token_program_id  # Use detected program ID
                    )
                    instructions.append(create_ata_ix)
                    destination_account = destination_ata
                    logger.info(f"ATA creation instruction added with program_id={token_program_id}")
                except Exception as e:
                    logger.error(f"Failed to create ATA instruction: {e}")
                    if is_token_2022:
                        logger.error("Token-2022: Cannot create ATA - mint may have restrictions. Recipient must have existing token account.")
                    else:
                        logger.error("Cannot create ATA for recipient")
                    return None
        else:
            destination_account = destination_ata
            logger.info(f"ATA already exists: {destination_ata}")
            
        # Fetch mint info to get decimals
        mint_info = client.get_account_info(mint)
        if mint_info.value is None:
            print(f"Mint {mint} does not exist")
            return None
            
        # Parse decimals from mint data (byte 44)
        try:
            decimals = mint_info.value.data[44]
        except:
            print("Could not parse decimals, defaulting to 9")
            decimals = 9
        
        amount_raw = int(amount_ui * 10**decimals)
        
        if amount_raw <= 0:
            print(f"Amount too small: {amount_ui}")
            return None
        
        # Use the dynamically detected token_program_id for transfer
        program_id = token_program_id
        logger.info(f"Using program ID: {program_id} for transfer")
        
        # For Token-2022, use transfer (not transfer_checked) as it's more compatible
        if is_token_2022:
            logger.info("Using transfer (not transfer_checked) for Token-2022")
            # Create transfer instruction manually to ensure correct program ID
            try:
                transfer_ix = transfer(
                    TransferParams(
                        program_id=program_id,
                        source=source_account,
                        dest=destination_account,
                        owner=sender_keypair.pubkey(),
                        amount=amount_raw
                    )
                )
                # Log instruction details for debugging
                logger.info(f"Transfer instruction created - Program ID: {transfer_ix.program_id}, Accounts: {len(transfer_ix.accounts)}")
                # Verify the instruction has the correct program ID
                if str(transfer_ix.program_id) != str(program_id):
                    logger.warning(f"Transfer instruction program ID mismatch: {transfer_ix.program_id} vs {program_id}")
                    # Force correct program ID
                    from solders.instruction import Instruction
                    transfer_ix = Instruction(
                        program_id=program_id,
                        accounts=transfer_ix.accounts,
                        data=transfer_ix.data
                    )
                    logger.info(f"Created new instruction with correct program ID: {transfer_ix.program_id}")
                instructions.append(transfer_ix)
            except Exception as e:
                logger.error(f"Failed to create transfer instruction for Token-2022: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None
        else:
            # For standard Token, use transfer_checked for better validation
            instructions.append(
                transfer_checked(
                    TransferCheckedParams(
                        program_id=program_id,
                        source=source_account,
                        mint=mint,
                        dest=destination_account,
                        owner=sender_keypair.pubkey(),
                        amount=amount_raw,
                        decimals=decimals
                    )
                )
            )
        
        # Fetch recent blockhash
        recent_blockhash = client.get_latest_blockhash().value.blockhash
        
        # Create Message
        msg = Message.new_with_blockhash(
            instructions,
            sender_keypair.pubkey(),
            recent_blockhash
        )
        
        # Create and sign Transaction
        txn = SoldersTransaction([sender_keypair], msg, recent_blockhash)
        
        # For Token-2022 with ATA creation, simulate first to check if it will fail
        if is_token_2022 and len(instructions) > 1:
            # Transaction includes ATA creation - simulate first to check if it will fail
            try:
                simulate_result = client.simulate_transaction(txn)
                if simulate_result.value:
                    if simulate_result.value.err:
                        error_msg = str(simulate_result.value.err)
                        if "Provided owner is not allowed" in error_msg or "IllegalOwner" in error_msg:
                            logger.error("Token-2022: Mint doesn't allow ATA creation for this recipient")
                            logger.error("Recipient must have an existing token account for this Token-2022 mint")
                            return None
                    # Check logs for IllegalOwner error
                    if simulate_result.value.logs:
                        for log in simulate_result.value.logs:
                            if "IllegalOwner" in log or "Provided owner is not allowed" in log:
                                logger.error("Token-2022: Mint doesn't allow ATA creation (detected in logs)")
                                logger.error("Recipient must have an existing token account for this Token-2022 mint")
                                return None
            except Exception as e:
                logger.warning(f"Simulation check failed: {e}, proceeding with transaction anyway")
        
        result = client.send_transaction(txn)
        if result.value:
            logger.info(f"✅ Token transfer successful: {result.value}")
            return result.value
        else:
            logger.error(f"❌ Token transfer returned None")
            return None
    except Exception as e:
        logger.error(f"❌ Transfer Token failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def get_token_info(ca: str):
    """Fetch token info from DexScreener."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
        response = requests.get(url)
        data = response.json()
        
        if data.get('pairs'):
            pair = data['pairs'][0]
            return {
                'price': pair.get('priceUsd', '0'),
                'mcap': pair.get('fdv', 0), # Fully Diluted Valuation as proxy for MC
                'liquidity': pair.get('liquidity', {}).get('usd', 0),
                'symbol': pair.get('baseToken', {}).get('symbol', 'Unknown')
            }
        return None
    except Exception as e:
        print(f"DexScreener API failed: {e}")
        return None
