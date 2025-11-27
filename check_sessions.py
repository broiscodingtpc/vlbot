"""Check sessions in database."""
import sqlite3

conn = sqlite3.connect('volumebot.db')
cursor = conn.cursor()

# Get all sessions
cursor.execute("SELECT id, token_ca, strategy, is_active, telegram_chat_id, total_volume_generated FROM sessions ORDER BY id DESC")
sessions = cursor.fetchall()

print(f"Total sessions: {len(sessions)}\n")

for session in sessions:
    session_id, token_ca, strategy, is_active, chat_id, volume = session
    print(f"Session ID: {session_id}")
    print(f"  Token CA: {token_ca[:20]}...")
    print(f"  Strategy: {strategy}")
    print(f"  Is Active: {is_active}")
    print(f"  Chat ID: {chat_id}")
    print(f"  Volume: ${volume:,.2f}")
    
    # Check sub-wallets
    cursor.execute("SELECT COUNT(*) FROM sub_wallets WHERE session_id = ?", (session_id,))
    sub_count = cursor.fetchone()[0]
    print(f"  Sub-wallets: {sub_count}")
    print()

conn.close()

