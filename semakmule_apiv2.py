# semakmule_apiv2.py
"""
Dummy SemakMule PDRM API for opensource bot.
Returns demo data based on config.DEMO_SEMAKMULE_POLICE_REPORTS flag.
Set DEMO_SEMAKMULE_POLICE_REPORTS=0 for clean results, or >0 to simulate police reports found.
"""

import logging
import config

logger = logging.getLogger(__name__)


def semakmule_lookup(search_type: str, value: str) -> dict:
    """Return a demo SemakMule lookup result."""
    police_reports = config.DEMO_SEMAKMULE_POLICE_REPORTS
    logger.info(f"[SemakMule] Demo lookup: type={search_type}, value={value}, police_reports={police_reports}")

    return {
        'ok': True,
        'category': search_type,
        'keyword': value,
        'search_count': police_reports,
        'police_reports': police_reports,
        'raw': {}
    }
