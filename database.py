# database.py
import sqlite3
import logging
from config import DB_NAME # Import dari config

logger = logging.getLogger(__name__)

def setup_database():
    """
    Cipta tables SQLite berdasarkan schema.
    Hanya akan cipta jika tables belum wujud.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # Guna 'executescript' untuk run berbilang arahan
        sql_schema = """
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            submitter_user_id TEXT NOT NULL,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL,
            description TEXT,
            reporter_status TEXT NOT NULL,
            report_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            amount_scammed REAL DEFAULT 0,
            report_against_type TEXT NOT NULL,
            against_phone_number TEXT,
            against_phone_name TEXT,
            against_bank_number TEXT,
            against_bank_holder_name TEXT,
            against_bank_name TEXT,
            against_social_url TEXT,
            additional_info TEXT,
            linked_profile_id TEXT, 
            FOREIGN KEY (linked_profile_id) REFERENCES profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS screenshots (
            screenshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            FOREIGN KEY (report_id) REFERENCES reports(report_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS profiles (
            profile_id TEXT PRIMARY KEY,
            main_identifier TEXT NOT NULL,
            unconfirmed_names TEXT,
            profile_image TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            stat_total_loss REAL DEFAULT 0,
            stat_total_reports INTEGER DEFAULT 0,
            stat_unique_banks INTEGER DEFAULT 0,
            stat_unique_phones INTEGER DEFAULT 0,
            stat_unique_socials INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS profile_bank_accounts (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            account_number TEXT NOT NULL,
            bank_name TEXT,
            holder_name TEXT,
            report_count INTEGER DEFAULT 1,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id) ON DELETE CASCADE,
            UNIQUE(profile_id, account_number)
        );

        CREATE TABLE IF NOT EXISTS profile_phone_numbers (
            phone_id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            report_count INTEGER DEFAULT 1,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id) ON DELETE CASCADE,
            UNIQUE(profile_id, phone_number)
        );

        CREATE TABLE IF NOT EXISTS profile_social_media (
            social_id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            url TEXT NOT NULL,
            platform_name TEXT,
            report_count INTEGER DEFAULT 1,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id) ON DELETE CASCADE,
            UNIQUE(profile_id, url)
        );
        
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_date DATETIME,
            last_active_datetime DATETIME
        );
        
        CREATE TABLE IF NOT EXISTS search_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            search_type TEXT,
            ip_address TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        
        """
        cursor.executescript(sql_schema)
        conn.commit()
        logger.info(f"Database '{DB_NAME}' berjaya disetup.")
    except sqlite3.Error as e:
        logger.error(f"Ralat semasa setup database: {e}")
    finally:
        if conn:
            conn.close()

def migrate_social_media_columns():
    """Add social tracker columns to profile_social_media."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    migrations = [
        ("profile_social_media", "extracted_username", "TEXT"),
        ("profile_social_media", "platform_user_id", "TEXT"),
        ("profile_social_media", "display_name", "TEXT"),
        ("profile_social_media", "profile_pic_url", "TEXT"),
        ("profile_social_media", "username_history", "TEXT"),
        ("profile_social_media", "lookup_status", "TEXT DEFAULT 'pending'"),
        ("profile_social_media", "last_checked_at", "DATETIME"),
        ("profile_social_media", "sec_uid", "TEXT"),
        ("profile_social_media", "hidden", "INTEGER DEFAULT 0"),
    ]
    for table, column, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info(f"Added column {column} to {table}")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_platform_user_id ON profile_social_media(platform_user_id)")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def migrate_reports_columns():
    """Add needs_info and rejection columns to reports."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    migrations = [
        ("reports", "needs_info_since", "DATETIME"),
        ("reports", "auto_rejected", "INTEGER DEFAULT 0"),
        ("reports", "restored_at", "DATETIME"),
        ("reports", "admin_note", "TEXT"),
        ("reports", "rejection_reason", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info(f"Added column {column} to {table}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def get_db_connection() -> sqlite3.Connection:
    """Helper function untuk dapatkan connection DB (dengan row_factory)."""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row 
    return conn