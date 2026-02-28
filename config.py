# config.py
import os
from dotenv import load_dotenv
load_dotenv()


def _require_env(name):
    """Get required environment variable or raise error."""
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}. See .env.example")
    return val


# === Bot Configuration ===
BOT_TOKEN = _require_env('BOT_TOKEN')
DB_NAME = "scam_reports.db"
MAX_SCREENSHOTS = 10
ADMIN_USER_IDS = [int(x) for x in os.environ.get('ADMIN_USER_IDS', '').split(',') if x.strip()]
REQUIRED_CHANNEL_ID = os.environ.get('REQUIRED_CHANNEL_ID', '@PenipuMYChannel')
REQUIRED_CHANNEL_URL = os.environ.get('REQUIRED_CHANNEL_URL', 'https://t.me/PenipuMYChannel')

# === Demo API Flags ===
# Set these to control what dummy APIs return.
# SemakMule: number of police reports returned (0 = clean, >0 = flagged)
DEMO_SEMAKMULE_POLICE_REPORTS = int(os.environ.get('DEMO_SEMAKMULE_POLICE_REPORTS', '0'))
# Truecaller: whether lookups return a name or "no data"
DEMO_TRUECALLER_FOUND = os.environ.get('DEMO_TRUECALLER_FOUND', 'true').lower() == 'true'
# Social Tracker: whether lookups return a resolved profile
DEMO_SOCIAL_TRACKER_FOUND = os.environ.get('DEMO_SOCIAL_TRACKER_FOUND', 'true').lower() == 'true'

# === Rate Limiting ===
# Toggle on/off + max lookups per window
RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'true').lower() == 'true'
RATE_LIMIT_MAX = int(os.environ.get('RATE_LIMIT_MAX', '2'))
RATE_LIMIT_WINDOW_HOURS = int(os.environ.get('RATE_LIMIT_WINDOW_HOURS', '5'))

# === Templates ===
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
VERIFIED_CARD_TEMPLATE = "card_verified.html"
UNVERIFIED_CARD_TEMPLATE = "card_unverified.html"


# === ConversationHandler States ===
# Report flow
(TITLE, DESCRIPTION, REPORTER_STATUS,
 REPORT_AGAINST_TYPE, GET_PHONE_DETAILS, GET_BANK_DETAILS, GET_SOCIAL_DETAILS,
 GET_AMOUNT, GET_SCREENSHOTS, CONFIRMATION) = range(10)  # 0-9

# Report additional info
(ADD_PHONE, ADD_BANK, ADD_SOCIAL) = range(10, 13)  # 10-12

# Search flow
(SEARCH_TERM, SEARCH_RESULTS, VIEW_PROFILE_REPORTS) = range(20, 23)  # 20-22

# Admin flow
(ADMIN_MENU, ADMIN_REVIEW_REPORT,
 ADMIN_LINK_PROFILE, ADMIN_NEW_PROFILE_NAME,
 ADMIN_NEEDS_INFO_REASON) = range(30, 35)  # 30-34

# Reporter update flow
(UPDATE_REPORT_DESC, UPDATE_REPORT_SCREENSHOTS, UPDATE_REPORT_CONFIRM) = range(40, 43)  # 40-42
