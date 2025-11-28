import requests
import base64
import logging
import json
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from config import JUPITER_API_URL

logger = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"

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

        self.quote_api = f"{JUPITER_API_URL}/quote"
        self.swap_api = f"{JUPITER_API_URL}/swap"
    
    def get_quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int = 50):
        """Get quote from Jupiter V6 API."""
        try:
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": slippage_bps,
                "onlyDirectRoutes": "false",
                "asLegacyTransaction": "false"
            }
            
            response = requests.get(self.quote_api, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Get quote failed: {e}")
            return None
    
    def get_swap_transaction(self, quote_response: dict):
        """Get swap transaction from Jupiter V6 API."""
        try:
            payload = {
                "quoteResponse": quote_response,
                "userPublicKey": str(self.keypair.pubkey()),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True, # V6 feature
                "prioritizationFeeLamports": "auto" # V6 feature
            }
            
            response = requests.post(self.swap_api, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Get swap transaction failed: {e}")
            try:
                if 'response' in locals():
                    logger.error(f"API Response: {response.text}")
            except:
                pass
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
