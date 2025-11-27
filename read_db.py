import sqlite3
import pandas as pd

def read_latest_session():
    conn = sqlite3.connect('volumebot.db')
    query = "SELECT * FROM sessions ORDER BY id DESC LIMIT 1"
    df = pd.read_sql_query(query, conn)
    print(df.to_string())
    conn.close()

if __name__ == "__main__":
    read_latest_session()
