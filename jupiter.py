import requests
import base64
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
import logging

logger = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"

class JupiterClient:
    def __init__(self, rpc_url: str, wallet_private_key: str):
        self.rpc_url = rpc_url
        self.client = Client(rpc_url)
        # Accept both base58 string (from to_base58_string) or bytes-encoded base58 (from b58encode)
        try:
            # Try from_base58_string first (standard Solana format)
            self.keypair = Keypair.from_base58_string(wallet_private_key)
        except Exception:
            # Fallback: if it's bytes-encoded base58, decode first then create from bytes
            import base58
            try:
                keypair_bytes = base58.b58decode(wallet_private_key)
                self.keypair = Keypair.from_bytes(keypair_bytes)
            except Exception as e:
                logger.error(f"Failed to load keypair: {e}")
                raise
        # Using public v6 API which has better token coverage
        self.quote_api = "https://lite-api.jup.ag/swap/v1/quote"
        self.swap_api = "https://lite-api.jup.ag/swap/v1/swap"
        self.swap_instructions_api = "https://lite-api.jup.ag/swap/v1/swap-instructions"
    
    def get_quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int = 50):
        """Get quote from Jupiter API."""
        try:
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": slippage_bps
            }
            
            response = requests.get(self.quote_api, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Get quote failed: {e}")
            return None
    
    def get_swap_transaction(self, quote_response: dict):
        """Get swap transaction from Jupiter API."""
        try:
            payload = {
                "quoteResponse": quote_response,
                "userPublicKey": str(self.keypair.pubkey()),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto"
            }
            
            response = requests.post(self.swap_api, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Get swap transaction failed: {e}")
            # Try to log the response text if available for debugging
            try:
                if 'response' in locals():
                    logger.error(f"API Response: {response.text}")
            except:
                pass
            return None

    def get_swap_instructions(self, quote_response: dict):
        """Get swap instructions from Jupiter API."""
        try:
            payload = {
                "quoteResponse": quote_response,
                "userPublicKey": str(self.keypair.pubkey()),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto"
            }
            
            response = requests.post(self.swap_instructions_api, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Get swap instructions failed: {e}")
            return None
    
    def execute_swap(self, swap_transaction_data: str):
        """Sign and send the swap transaction."""
        try:
            # Decode base64 transaction
            raw_txn = base64.b64decode(swap_transaction_data)
            
            # Deserialize as VersionedTransaction
            txn = VersionedTransaction.from_bytes(raw_txn)
            
            # Sign transaction - VersionedTransaction needs to be signed via message signing
            signature = self.keypair.sign_message(bytes(txn.message))
            # Replace the first signature (payer signature)
            txn.signatures[0] = signature
            
            # Send transaction
            result = self.client.send_raw_transaction(bytes(txn))
            
            return result.value
        except Exception as e:
            logger.error(f"Execute swap failed: {e}")
            import traceback
            traceback.print_exc()
            return None
