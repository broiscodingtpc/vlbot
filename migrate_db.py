"""Migration script to add telegram_chat_id column to sessions table."""
import sqlite3
import os
from config import DB_PATH

# Extract database path from SQLAlchemy connection string
db_path = DB_PATH.replace('sqlite:///', '')

if not os.path.exists(db_path):
    print(f"Database file {db_path} does not exist. Creating new database...")
    from database import init_db
    init_db()
    print("Database created successfully!")
else:
    print(f"Migrating database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'telegram_chat_id' not in columns:
            print("Adding telegram_chat_id column to sessions table...")
            cursor.execute("ALTER TABLE sessions ADD COLUMN telegram_chat_id TEXT")
            conn.commit()
            print("[OK] Migration completed successfully!")
        else:
            print("[OK] Column telegram_chat_id already exists. No migration needed.")
    except Exception as e:
        print(f"[ERROR] Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

print("Migration script finished.")

