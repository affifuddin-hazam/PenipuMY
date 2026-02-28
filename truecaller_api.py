# truecaller_api.py
"""
Dummy Truecaller API for opensource bot.
Returns demo data based on config.DEMO_TRUECALLER_FOUND flag.
Set DEMO_TRUECALLER_FOUND=true to simulate a name found, or false for no record.
"""

import logging
import config

logger = logging.getLogger(__name__)

MAX_FAIL_COUNT = 3


class TruecallerAPI:
    """Dummy Truecaller API that returns demo results."""

    async def lookup(self, phone_number: str, country_code: str = "my") -> dict:
        """Return a demo lookup result based on config flag."""
        logger.info(f"[TruecallerAPI] Demo lookup for {phone_number}")

        if config.DEMO_TRUECALLER_FOUND:
            return {
                'status': 'success',
                'name': 'Demo User',
                'carrier': 'Demo Carrier',
                'is_spam': False,
                'spam_type': None
            }
        else:
            return {
                'status': 'no_data',
                'name': None,
                'carrier': None,
                'is_spam': False,
                'spam_type': None,
                'message': 'No record found on Truecaller.'
            }

    def _load_sessions(self) -> dict:
        """Return empty sessions (no real sessions in demo mode)."""
        return {'sessions': []}
