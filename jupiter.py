import requests
import base64
import logging
import json
import time
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from config import JUPITER_API_URL

logger = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Fallback Jupiter API endpoints
JUPITER_V6_API = "https://quote-api.jup.ag/v6"
JUPITER_V5_API = "https://quote-api.jup.ag/v5"  # Fallback to V5
JUPITER_V4_API = "https://quote-api.jup.ag/v4"  # Fallback to V4
JUPITER_ALTERNATIVE = "https://api.jup.ag/swap/v1"  # Alternative endpoint

class JupiterClient:
    def __init__(self, rpc_url: str, wallet_private_key: str):
        self.rpc_url = rpc_url
        self.client = Client(rpc_url)
        
        # Initialize Keypair
        try:
            # Try from_base58_string first (standard Solana format)
            self.keypair = Keypair.from_base58_string(wallet_private_key)
        except Exception:
            # Fallback: if it's bytes-encoded base58
            import base58
            try:
                keypair_bytes = base58.b58decode(wallet_private_key)
                self.keypair = Keypair.from_bytes(keypair_bytes)
            except Exception as e:
                logger.error(f"Failed to load keypair: {e}")
                raise

        # Use configured URL or default to V6
        base_url = JUPITER_API_URL if JUPITER_API_URL else JUPITER_V6_API
        self.quote_api = f"{base_url}/quote"
        self.swap_api = f"{base_url}/swap"
        
        # Fallback endpoints
        self.fallback_endpoints = [
            (JUPITER_V6_API, "v6"),
            (JUPITER_V5_API, "v5"),
            (JUPITER_V4_API, "v4"),
            (JUPITER_ALTERNATIVE, "v1")
        ]
    
    def get_quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int = 50):
        """Get quote from Jupiter API with fallback to multiple endpoints."""
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": "false",
            "asLegacyTransaction": "false"
        }
        
        # Try primary endpoint first
        quote = self._try_get_quote(self.quote_api, params, "primary")
        if quote:
            return quote
        
        # Try fallback endpoints
        logger.warning("⚠️ Primary Jupiter endpoint failed, trying fallback endpoints...")
        for base_url, version in self.fallback_endpoints:
            if base_url in self.quote_api:
                continue  # Skip if already tried
            
            fallback_quote_api = f"{base_url}/quote"
            logger.info(f"🔄 Trying Jupiter {version} API...")
            quote = self._try_get_quote(fallback_quote_api, params, version)
            if quote:
                # Update APIs to use this working endpoint
                self.quote_api = fallback_quote_api
                self.swap_api = f"{base_url}/swap"
                logger.info(f"✅ Switched to Jupiter {version} API")
                return quote
        
        logger.error("❌ All Jupiter endpoints failed")
        return None
    
    def _try_get_quote(self, quote_api_url: str, params: dict, endpoint_name: str):
        """Try to get quote from a specific endpoint."""
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Jupiter {endpoint_name} API: Getting quote (attempt {attempt + 1}/{MAX_RETRIES})...")
                response = requests.get(
                    quote_api_url, 
                    params=params, 
                    timeout=15,
                    headers={'User-Agent': 'KodeS-VolumeBot/1.0'}
                )
                response.raise_for_status()
                quote_data = response.json()
                logger.info(f"✅ Jupiter {endpoint_name} quote received successfully")
                return quote_data
            except requests.exceptions.ConnectionError as e:
                error_msg = str(e)
                if "Failed to resolve" in error_msg or "NameResolutionError" in error_msg:
                    logger.warning(f"⚠️ DNS resolution failed for Jupiter {endpoint_name} API (attempt {attempt + 1}/{MAX_RETRIES})")
                else:
                    logger.warning(f"⚠️ Connection error to Jupiter {endpoint_name} API (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.info(f"⏳ Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Jupiter {endpoint_name} quote failed after {MAX_RETRIES} attempts")
            except requests.exceptions.Timeout as e:
                logger.warning(f"⚠️ Request timeout for Jupiter {endpoint_name} API (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.info(f"⏳ Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Jupiter {endpoint_name} quote failed: Timeout")
            except requests.exceptions.HTTPError as e:
                logger.warning(f"⚠️ HTTP error from Jupiter {endpoint_name} API: {e}")
                if hasattr(e.response, 'text'):
                    logger.warning(f"Response: {e.response.text[:200]}")
                return None  # Try next endpoint
            except Exception as e:
                logger.warning(f"⚠️ Jupiter {endpoint_name} quote error: {e}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    time.sleep(wait_time)
                else:
                    return None
        
        return None
    
    def get_swap_transaction(self, quote_response: dict):
        """Get swap transaction from Jupiter API with retry logic."""
        # Determine API version based on current endpoint
        is_v6 = "v6" in self.swap_api
        is_v5 = "v5" in self.swap_api
        
        payload = {
            "quoteResponse": quote_response,
            "userPublicKey": str(self.keypair.pubkey()),
            "wrapAndUnwrapSol": True,
        }
        
        # V6 specific features
        if is_v6:
            payload["dynamicComputeUnitLimit"] = True
            payload["prioritizationFeeLamports"] = "auto"
        # V5 and below use different format
        elif is_v5:
            payload["dynamicComputeUnitLimit"] = True
        else:
            # V4 and below
            payload["asLegacyTransaction"] = False
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Jupiter API: Getting swap transaction (attempt {attempt + 1}/{MAX_RETRIES})...")
                response = requests.post(
                    self.swap_api, 
                    json=payload, 
                    timeout=15,
                    headers={'User-Agent': 'KodeS-VolumeBot/1.0', 'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                swap_data = response.json()
                logger.info(f"✅ Jupiter swap transaction received successfully")
                return swap_data
            except requests.exceptions.ConnectionError as e:
                error_msg = str(e)
                if "Failed to resolve" in error_msg or "NameResolutionError" in error_msg:
                    logger.warning(f"⚠️ DNS resolution failed for Jupiter API (attempt {attempt + 1}/{MAX_RETRIES})")
                else:
                    logger.warning(f"⚠️ Connection error to Jupiter API (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.info(f"⏳ Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Get swap transaction failed after {MAX_RETRIES} attempts: {e}")
            except requests.exceptions.Timeout as e:
                logger.warning(f"⚠️ Request timeout (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.info(f"⏳ Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Get swap transaction failed after {MAX_RETRIES} attempts: Timeout")
            except requests.exceptions.HTTPError as e:
                logger.error(f"❌ HTTP error from Jupiter API: {e}")
                try:
                    if hasattr(e, 'response') and e.response:
                        logger.error(f"Response status: {e.response.status_code}")
                        logger.error(f"Response body: {e.response.text[:500]}")
                except:
                    pass
                return None
            except Exception as e:
                logger.error(f"❌ Get swap transaction failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None
        
        return None

    def execute_swap(self, swap_transaction_data: str):
        """Sign and send the swap transaction."""
        try:
            # Decode base64 transaction
            raw_txn = base64.b64decode(swap_transaction_data)
            
            # Deserialize as VersionedTransaction
            txn = VersionedTransaction.from_bytes(raw_txn)
            
            # Sign transaction
            message_bytes = bytes(txn.message)
            signature = self.keypair.sign_message(message_bytes)
            
            # For VersionedTransaction, we need to sign properly
            # Jupiter V6 returns a transaction that just needs our signature
            # We can use solders to sign it easily
            
            # Create a new list of signatures
            # Usually the payer is the first signer
            txn_signatures = list(txn.signatures)
            txn_signatures[0] = signature # Replace the first signature (payer)
            
            # Update the transaction with the new signature
            # Note: VersionedTransaction fields are often immutable directly, 
            # but we can create a new one or modify if the library allows.
            # Solders VersionedTransaction allows modifying signatures list if it's a list
            
            # Actually, solders VersionedTransaction.populate(message, signatures) is the way,
            # or just constructing it.
            # But simpler: txn is already constructed, just need to fill the signature.
            
            # Let's try the robust way:
            # We need to find our index in the static account keys to be sure, 
            # but usually Jupiter sets user as payer (index 0).
            
            txn = VersionedTransaction(txn.message, [signature])
            
            # Send transaction
            opts = self.client.api.types.TxOpts(skip_preflight=True)
            result = self.client.send_transaction(txn, opts=opts)
            
            if result.value:
                logger.info(f"✅ Swap transaction sent: {result.value}")
                return result.value
            else:
                logger.error(f"Transaction send returned None: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Execute swap failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
