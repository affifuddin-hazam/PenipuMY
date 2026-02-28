# rate_limit.py
"""
In-memory per-user rate limiting for Truecaller lookups.
Configurable via config.py:
  RATE_LIMIT_ENABLED  — toggle on/off (default: true)
  RATE_LIMIT_MAX      — max lookups per window (default: 2)
  RATE_LIMIT_WINDOW_HOURS — window duration in hours (default: 5)
Resets on bot restart (acceptable for bot context).
"""

import time
import logging
from typing import Dict, Tuple, Optional

import config

logger = logging.getLogger(__name__)

_rate_limit_store: Dict[int, list] = {}


def _cleanup_expired(user_id: int) -> list:
    """Remove expired timestamps for a user."""
    window_seconds = config.RATE_LIMIT_WINDOW_HOURS * 3600
    now = time.time()
    timestamps = _rate_limit_store.get(user_id, [])
    valid = [ts for ts in timestamps if (now - ts) < window_seconds]
    _rate_limit_store[user_id] = valid
    return valid


def rate_limit_check(user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Check if user has remaining Truecaller lookups.
    Returns (allowed: bool, message: Optional[str])
    Does NOT increment the counter.
    """
    if not config.RATE_LIMIT_ENABLED:
        return True, None

    valid = _cleanup_expired(user_id)

    if len(valid) >= config.RATE_LIMIT_MAX:
        window_seconds = config.RATE_LIMIT_WINDOW_HOURS * 3600
        oldest = min(valid)
        remaining_seconds = window_seconds - (time.time() - oldest)
        hours = int(remaining_seconds // 3600)
        minutes = int((remaining_seconds % 3600) // 60) + 1
        time_str = ""
        if hours > 0:
            time_str += f"{hours}h "
        time_str += f"{minutes}m"
        return False, f"Individual limit reached, try again in {time_str}"

    return True, None


def rate_limit_increment(user_id: int):
    """
    Record a successful Truecaller lookup for rate limiting.
    Call ONLY after a successful live API lookup (not cache hits, not skips, not errors).
    """
    if not config.RATE_LIMIT_ENABLED:
        return

    if user_id not in _rate_limit_store:
        _rate_limit_store[user_id] = []
    _rate_limit_store[user_id].append(time.time())
    logger.info(f"[RateLimit] User {user_id} Truecaller count: {len(_rate_limit_store[user_id])}")
