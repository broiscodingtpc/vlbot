from database import get_db, Session as DBSession, SubWallet
import base58

def export_keys():
    db = next(get_db())
    sessions = db.query(DBSession).all()
    
    print(f"{'SESSION ID':<10} | {'TYPE':<15} | {'ADDRESS':<44} | {'PRIVATE KEY (Base58)'}")
    print("-" * 120)
    
    for s in sessions:
        # Deposit Wallet
        print(f"{s.id:<10} | {'Deposit':<15} | {s.deposit_wallet_address:<44} | {s.deposit_wallet_private_key}")
        
        # Sub Wallets
        subs = db.query(SubWallet).filter(SubWallet.session_id == s.id).all()
        for sub in subs:
            print(f"{s.id:<10} | {'Sub-Wallet':<15} | {sub.address:<44} | {sub.private_key}")

if __name__ == "__main__":
    export_keys()
