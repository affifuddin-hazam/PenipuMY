import sqlite3
import json
from datetime import datetime
from database import get_db_connection

def init_truecaller_table():
    """Create truecaller_cache table if not exists"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS truecaller_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL UNIQUE,
            name TEXT,
            carrier TEXT,
            is_spam BOOLEAN DEFAULT 0,
            spam_type TEXT,
            raw_result TEXT,
            looked_up_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            looked_up_by INTEGER
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_truecaller_phone
        ON truecaller_cache(phone_number)
    """)

    conn.commit()
    conn.close()


def save_truecaller_result(phone_number: str, result: dict, user_id: int = None):
    """Save Truecaller lookup result to database"""
    if result.get('status') != 'success':
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO truecaller_cache
            (phone_number, name, carrier, is_spam, spam_type, raw_result, looked_up_by, looked_up_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            phone_number,
            result.get('name'),
            result.get('carrier'),
            1 if result.get('is_spam') else 0,
            result.get('spam_type'),
            json.dumps(result),
            user_id
        ))

        conn.commit()

    except Exception as e:
        print(f"Failed to save Truecaller result: {e}")
        conn.rollback()

    finally:
        conn.close()


def get_truecaller_cache(phone_number: str) -> dict:
    """Get cached Truecaller result from database"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, carrier, is_spam, spam_type, looked_up_at
        FROM truecaller_cache
        WHERE phone_number = ?
    """, (phone_number,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'status': 'cached',
            'name': row[0],
            'carrier': row[1],
            'is_spam': bool(row[2]),
            'spam_type': row[3],
            'looked_up_at': row[4]
        }

    return None


# Initialize table on import
init_truecaller_table()
