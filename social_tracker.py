# social_tracker.py
"""
Social Media ID Tracker for opensource bot.
parse_social_url() — real URL parser (no external API).
SocialTracker — dummy that returns demo data based on config.DEMO_SOCIAL_TRACKER_FOUND flag.
Set DEMO_SOCIAL_TRACKER_FOUND=true to simulate resolved profile, or false for not found.
"""

import re
import logging
from typing import Dict

import config

logger = logging.getLogger(__name__)


# ============================================================
#  URL PARSER (real — pure string parsing, no API calls)
# ============================================================

def parse_social_url(url: str) -> Dict:
    """
    Detect platform and extract username from a social media URL.
    Returns: {platform, username, original_url}
    """
    if not url:
        return {'platform': 'unknown', 'username': None, 'original_url': url}

    url_clean = url.strip()

    # Normalize: add https if no scheme
    url_for_parse = url_clean
    if not url_for_parse.startswith(('http://', 'https://')):
        url_for_parse = 'https://' + url_for_parse

    patterns = [
        # Instagram profile (exclude /p/, /reel/, /stories/, /explore/)
        (r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?(?:\?.*)?$',
         'instagram', None),
        # Threads profile or post (extract @username from any threads.net/threads.com URL)
        (r'(?:https?://)?(?:www\.)?threads\.(?:net|com)/@([a-zA-Z0-9_.]+)',
         'threads', None),
        # TikTok profile
        (r'(?:https?://)?(?:www\.)?tiktok\.com/@([a-zA-Z0-9_.]+)/?(?:\?.*)?$',
         'tiktok', None),
        # Telegram
        (r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]+)/?(?:\?.*)?$',
         'telegram', None),
        (r'(?:https?://)?(?:www\.)?telegram\.me/([a-zA-Z0-9_]+)/?(?:\?.*)?$',
         'telegram', None),
        # Facebook profile.php?id=NUMERIC_ID
        (r'(?:https?://)?(?:www\.)?facebook\.com/profile\.php\?id=(\d+)',
         'facebook', None),
        # Facebook /p/ page URLs (e.g., /p/Page-Name-12345/)
        (r'(?:https?://)?(?:www\.)?facebook\.com/p/([^/?]+?)/?(?:\?.*)?$',
         'facebook', None),
        # Facebook regular username/page
        (r'(?:https?://)?(?:www\.)?facebook\.com/([a-zA-Z0-9_.]+)/?(?:\?.*)?$',
         'facebook', None),
        # Twitter / X
        (r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)/?(?:\?.*)?$',
         'twitter', None),
    ]

    # Exclude known non-profile paths
    exclude_paths = {
        'instagram': {'p', 'reel', 'reels', 'stories', 'explore', 'accounts', 'about', 'legal', 'developer', 'directory'},
        'tiktok': {'video', 'music', 'tag', 'discover', 'live'},
        'telegram': {'s', 'addstickers', 'joinchat', 'addtheme'},
        'facebook': {'watch', 'marketplace', 'groups', 'events', 'pages', 'gaming', 'stories', 'profile.php', 'photo', 'video', 'reel', 'share', 'login', 'help'},
        'twitter': {'search', 'explore', 'settings', 'i', 'home', 'notifications', 'messages'},
    }

    for pattern, platform, _ in patterns:
        match = re.match(pattern, url_clean, re.IGNORECASE)
        if match:
            username = match.group(1)
            # Check if it's actually a profile (not a sub-page)
            excluded = exclude_paths.get(platform, set())
            if username.lower() in excluded:
                continue
            return {
                'platform': platform,
                'username': username,
                'original_url': url_clean
            }

    return {'platform': 'unknown', 'username': None, 'original_url': url_clean}


# ============================================================
#  SOCIAL TRACKER (dummy — returns demo data based on config)
# ============================================================

class SocialTracker:
    """Dummy social media ID tracker. Returns demo results based on config flag."""

    def lookup(self, username: str, platform: str) -> Dict:
        """Return a demo lookup result based on config flag."""
        logger.info(f"[SocialTracker] Demo lookup: @{username} on {platform}")

        if config.DEMO_SOCIAL_TRACKER_FOUND:
            return {
                'status': 'success',
                'platform': platform,
                'username': username,
                'platform_user_id': f'demo_{platform}_{username}',
                'display_name': f'Demo ({username})',
                'profile_pic_url': None
            }
        else:
            return {
                'status': 'not_found',
                'platform': platform,
                'username': username,
                'platform_user_id': None,
                'display_name': None,
                'profile_pic_url': None,
                'message': 'Account not found.'
            }
