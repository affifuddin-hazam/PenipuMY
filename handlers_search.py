# handlers_search.py
import logging
import json
import re
import sqlite3
from datetime import datetime
from typing import Union, List, Dict, Any
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    InputMediaPhoto
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

# Import dari fail lain
import asyncio
import config
from database import get_db_connection
from bot_utils import _safe_edit_message, _safe_delete_message, _format_confirmation_message
from image_generator import generate_profile_image
from handlers_general import start # Perlu untuk 'cancel'
from semakmule_apiv2 import semakmule_lookup
from truecaller_api import TruecallerAPI
from truecaller_db import get_truecaller_cache, save_truecaller_result
from social_tracker import parse_social_url, SocialTracker
from rate_limit import rate_limit_check, rate_limit_increment
from typing import Optional

logger = logging.getLogger(__name__)

SEMAKMULE_ERROR_MSG = (
    "Unable to retrieve data from SemakMule at the moment.\n"
    "This does not indicate a clean or flagged status."
)

def _sanitize_phone_number(phone: str) -> str:
    """Sanitize phone number to standard format (0XXXXXXXXX)"""
    # Remove spaces, dashes, plus signs
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")

    # Convert 60XXXXXXXXX to 0XXXXXXXXX
    if phone.startswith("60"):
        phone = "0" + phone[2:]

    return phone

def _detect_search_type(term: str) -> Optional[str]:
    t = term.strip().replace(" ", "").replace("-", "").replace("+", "")

    # Malaysia phone

    #if re.fullmatch(r"(?:0?1\d{9}|60\d{9,10})", t):
    if re.fullmatch(r"(?:\+?60|0)1\d{8,9}", t):
        return "phone"

    # Bank account (digits only)
    if t.isdigit() and 8 <= len(t) <= 20:
        return "bank"

    return None


def _detect_social_media(term: str) -> Optional[Dict]:
    """Detect if search term is a social media URL/username. Returns parsed result or None."""
    if '.' in term or '/' in term:
        result = parse_social_url(term)
        if result.get('platform') != 'unknown' and result.get('username'):
            return result
    if term.startswith('@') and len(term) > 1:
        return {'platform': 'unknown', 'username': term[1:], 'original_url': term}
    return None


def _find_by_platform_user_id(platform_user_id: str, platform: str) -> List[Dict]:
    """Search profile_social_media by permanent platform_user_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Normalize platform variants
        platform_variants = [platform.lower(), platform.capitalize(), platform.upper()]
        if platform.lower() in ('instagram', 'threads'):
            platform_variants.extend(['instagram', 'Instagram', 'threads', 'Threads'])
        placeholders = ','.join(['?'] * len(platform_variants))
        cursor.execute(f"""
            SELECT p.*, ps.platform_user_id, ps.extracted_username, ps.display_name AS social_display_name,
                   ps.platform_name, ps.url AS social_url
            FROM profiles p
            JOIN profile_social_media ps ON p.profile_id = ps.profile_id
            WHERE ps.platform_user_id = ? AND LOWER(ps.platform_name) IN ({','.join(['?' for _ in platform_variants])})
        """, (platform_user_id, *[v.lower() for v in platform_variants]))
        results = cursor.fetchall()
        return [{key: row[key] for key in row.keys()} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error searching by platform_user_id: {e}")
        return []
    finally:
        conn.close()


async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    user_id = user.id
    logger.info(f"{user_id} entered search.")
    await query.answer()
    
    context.user_data['in_search_mode'] = True
    
    text = (
        "**Search**\n\n"
        "You may use any of the following information to perform a search:\n\n"
        "• Phone Number\n"
        "• Bank Account Number\n"
        "• Individual / Entity Name\n"
        "• Social Media Username / URL\n"
        "• DuitNow QR Image\n\n"
        "_A minimum of 4 characters is required for each search._"
    )


    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu_from_search")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=reply_markup
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id
    
    return config.SEARCH_TERM

def _find_matching_profiles(term: str) -> List[Dict[str, Any]]:
    query = """
    SELECT p.*
    FROM profiles p
    LEFT JOIN profile_bank_accounts pb ON p.profile_id = pb.profile_id
    LEFT JOIN profile_phone_numbers pp ON p.profile_id = pp.profile_id
    LEFT JOIN profile_social_media ps ON p.profile_id = ps.profile_id
    LEFT JOIN reports rp ON p.profile_id = rp.linked_profile_id
    WHERE 
        p.main_identifier LIKE ? OR
        p.unconfirmed_names LIKE ? OR
        pb.account_number LIKE ? OR
        pb.holder_name LIKE ? OR
        pp.phone_number LIKE ? OR
        ps.url LIKE ? OR
        rp.additional_info LIKE ?
    GROUP BY p.profile_id
    """
    like_term = f"%{term}%"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, [like_term] * 7)
        #cursor.execute(query, (like_term, like_term, like_term, like_term, like_term, like_term))
        results = cursor.fetchall()
        return [{key: row[key] for key in row.keys()} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error DB semasa cari 'matching profiles': {e}")
        return []
    finally:
        conn.close()

def _find_matching_reports(term: str) -> List[Dict[str, Any]]:
    query = """
    SELECT *
    FROM reports
    WHERE 
        (
            against_phone_number LIKE ? OR
            against_phone_name LIKE ? OR
            against_bank_number LIKE ? OR
            against_bank_holder_name LIKE ? OR
            against_social_url LIKE ? OR
            additional_info LIKE ? OR
            title LIKE ?
        )
        AND report_status = 'UNVERIFIED'
    ORDER BY submitted_at DESC
    """
    like_term = f"%{term}%"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, (like_term, like_term, like_term, like_term, like_term, like_term, like_term))
        results = cursor.fetchall()
        return [{key: row[key] for key in row.keys()} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error DB semasa cari 'matching reports': {e}")
        return []
    finally:
        conn.close()

async def search_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception:
        pass

    search_term = update.message.text
    prompt_id = context.user_data.get('prompt_message_id')
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    logger.info(f"{user_id} searched for {search_term}.")

    if len(search_term) < 4:
        await _safe_edit_message(
            context, chat_id, prompt_id,
            text=(
                "**Search**\n\n"
                "❌ **Search term is too short.** Please enter at least 4 characters. "
                "\n\n"
                "Please re-enter your search:"
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu_from_search")]]
            )
        )
        return config.SEARCH_TERM

    await _safe_edit_message(
        context, chat_id, prompt_id,
        text=f"⏳ Searching for `{search_term}`...",
        reply_markup=None,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # === Detect & call SemakMule FIRST ===
    search_type = _detect_search_type(search_term)
    
    log_type = search_type if search_type else "mixed"
    
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO search_logs (query, search_type, ip_address) VALUES (?, ?, ?)", 
            (search_term, log_type, f"Telegram:{user_id}")
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Search logging failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
    
    semakmule_result = None


    if search_type in ("phone", "bank"):
        semakmule_result = semakmule_lookup(search_type, search_term)

    context.user_data["semakmule"] = semakmule_result

    # === Social Media ID Tracking ===
    social_parse = _detect_social_media(search_term)
    social_lookup_result = None
    username_change_warning = None

    if social_parse and social_parse.get('platform') != 'unknown':
        tracker = SocialTracker()
        try:
            social_lookup_result = await asyncio.to_thread(
                tracker.lookup, social_parse['username'], social_parse['platform']
            )
        except Exception as e:
            logger.error(f"SocialTracker lookup failed: {e}")
            social_lookup_result = {'status': 'error', 'message': str(e)}

        if social_lookup_result and social_lookup_result.get('status') == 'success':
            pid = social_lookup_result.get('platform_user_id')
            platform = social_lookup_result.get('platform')
            if pid:
                # Check for username change in DB
                try:
                    conn_check = get_db_connection()
                    cursor_check = conn_check.cursor()
                    cursor_check.execute("""
                        SELECT extracted_username FROM profile_social_media
                        WHERE platform_user_id = ? AND LOWER(platform_name) = LOWER(?)
                    """, (pid, platform))
                    db_row = cursor_check.fetchone()
                    if db_row and db_row['extracted_username']:
                        current_username = social_lookup_result.get('username', '')
                        if db_row['extracted_username'].lower() != current_username.lower():
                            username_change_warning = (db_row['extracted_username'], current_username)
                            # Auto-update username in DB
                            cursor_check.execute("""
                                UPDATE profile_social_media
                                SET extracted_username = ?, last_checked_at = CURRENT_TIMESTAMP
                                WHERE platform_user_id = ? AND LOWER(platform_name) = LOWER(?)
                            """, (current_username, pid, platform))
                            conn_check.commit()
                    conn_check.close()
                except Exception:
                    pass

                # Search by permanent platform_user_id
                pid_matches = _find_by_platform_user_id(pid, platform)
                if pid_matches:
                    # Add these as profile results (avoid duplicates)
                    existing_pids = {p.get('profile_id') for _, p in [] if True}
                    for m in pid_matches:
                        if m.get('profile_id') not in [p.get('profile_id') for _, p in []]:
                            pass  # Will be found by normal profile search too

                # Auto-add to tracker if not already tracked
                try:
                    conn_add = get_db_connection()
                    cursor_add = conn_add.cursor()
                    cursor_add.execute(
                        "SELECT social_id FROM profile_social_media WHERE platform_user_id = ? AND LOWER(platform_name) = LOWER(?)",
                        (pid, platform)
                    )
                    if not cursor_add.fetchone():
                        url_map = {
                            'instagram': f'https://www.instagram.com/{social_lookup_result.get("username")}',
                            'threads': f'https://www.threads.net/@{social_lookup_result.get("username")}',
                            'tiktok': f'https://www.tiktok.com/@{social_lookup_result.get("username")}',
                            'telegram': f'https://t.me/{social_lookup_result.get("username")}',
                            'facebook': f'https://www.facebook.com/{social_lookup_result.get("username")}',
                            'twitter': f'https://x.com/{social_lookup_result.get("username")}',
                        }
                        auto_url = url_map.get(platform, search_term)
                        cursor_add.execute("""
                            INSERT INTO profile_social_media
                                (profile_id, url, platform_name, extracted_username, platform_user_id,
                                 display_name, profile_pic_url, report_count, lookup_status, last_checked_at)
                            VALUES ('__manual__', ?, ?, ?, ?, ?, ?, 0, 'success', CURRENT_TIMESTAMP)
                        """, (auto_url, platform.capitalize(), social_lookup_result.get('username'),
                              pid, social_lookup_result.get('display_name'),
                              social_lookup_result.get('profile_pic_url')))
                        conn_add.commit()
                        logger.info(f"[SocialTracker] Auto-added @{social_lookup_result.get('username')} ({platform}) to tracker")
                    conn_add.close()
                except Exception as e:
                    logger.warning(f"[SocialTracker] Auto-add failed: {e}")

    context.user_data["social_tracker"] = social_lookup_result
    context.user_data["username_change_warning"] = username_change_warning

    # === Truecaller Check (for phone numbers only) ===
    truecaller_result = None

    logger.info(f"[DEBUG] search_type = {search_type}, search_term = {search_term}")

    if search_type == "phone":
        logger.info(f"[DEBUG] Entering Truecaller check for phone: {search_term}")
        # Sanitize phone number
        sanitized_phone = _sanitize_phone_number(search_term)
        logger.info(f"[DEBUG] Sanitized phone: {sanitized_phone}")

        # Check cache first
        logger.info(f"[DEBUG] Checking cache for: {sanitized_phone}")
        cached = get_truecaller_cache(sanitized_phone)
        logger.info(f"[DEBUG] Cache result: {cached}")

        if cached:
            logger.info(f"[DEBUG] Using cached result")
            truecaller_result = cached
        else:
            # Check if phone number already exists in local reports DB
            # If it does, skip live Truecaller lookup to save rate limit
            phone_in_reports = False
            try:
                rconn = get_db_connection()
                rcursor = rconn.cursor()
                rcursor.execute(
                    "SELECT 1 FROM reports WHERE against_phone_number = ? LIMIT 1",
                    (sanitized_phone,)
                )
                phone_in_reports = rcursor.fetchone() is not None
                rconn.close()
            except Exception:
                pass

            if phone_in_reports:
                logger.info(f"[DEBUG] Phone {sanitized_phone} already in reports DB, skipping live Truecaller lookup")
                truecaller_result = {
                    'status': 'skipped',
                    'message': 'API call not initiated to conserve resources.'
                }
            else:
                # Check rate limit before live lookup
                allowed, limit_msg = rate_limit_check(user_id)
                if not allowed:
                    truecaller_result = {
                        'status': 'rate_limited',
                        'message': limit_msg
                    }
                else:
                    # Do fresh lookup — this is a truly unknown number
                    logger.info(f"[DEBUG] No cache & not in reports, doing fresh Truecaller lookup")
                    try:
                        api = TruecallerAPI()
                        logger.info(f"[DEBUG] TruecallerAPI initialized, calling lookup...")
                        truecaller_result = await api.lookup(sanitized_phone)
                        logger.info(f"[DEBUG] Lookup completed, result status: {truecaller_result.get('status')}")

                        # Save to DB if successful + increment rate limit
                        if truecaller_result.get('status') == 'success' and truecaller_result.get('name'):
                            save_truecaller_result(sanitized_phone, truecaller_result, user_id)
                            rate_limit_increment(user_id)
                        elif truecaller_result.get('status') in ('success', 'no_data'):
                            # Count successful lookups even without name
                            rate_limit_increment(user_id)

                    except Exception as e:
                        # Failed lookups do NOT count towards rate limit
                        logger.error(f"Truecaller lookup failed: {e}")
                        logger.error(f"[DEBUG] Exception details:", exc_info=True)
                        truecaller_result = {
                            'status': 'error',
                            'message': f'Truecaller check failed: {str(e)}'
                        }

    logger.info(f"[DEBUG] Final truecaller_result: {truecaller_result}")
    context.user_data["truecaller"] = truecaller_result
    
    matching_profiles = _find_matching_profiles(search_term)
    matching_reports = _find_matching_reports(search_term)
    
    all_results = []
    for profile in matching_profiles:
        all_results.append(("profile", profile))
    
    for report in matching_reports:
        #if report.get('linked_profile_id') not in [p['profile_id'] for p in matching_profiles]:
        #    all_results.append(("report", report))
        all_results.append(("report", report))

    if not all_results:
        sem = context.user_data.get("semakmule")
        tc = context.user_data.get("truecaller")

        text = (
            f"No result found for: `{search_term}`.\n\n"
            "Please try using a different keyword or identifier."
        )

        if sem:
            text += "\n\n———\n\n"
            if sem.get("ok"):
                text += (
                    "**SemakMule Check Result**\n"
                    f"Search Count     : {sem.get('search_count', 0)}\n"
                    f"Police Reports   : {sem.get('police_reports', 0)}"
                )
            else:
                text += (
                    "**SemakMule Check Result**\n"
                    "Unable to retrieve data from SemakMule at the moment.\n"
                    "_This does not indicate a clean or flagged status._"
                )

        # Add Truecaller result
        if tc:
            text += "\n\n———\n\n"

            if tc.get('status') == 'cooldown':
                text += (
                    "**Truecaller**\n"
                    f"API cooling down. Try again in {tc.get('cooldown_remaining', 0)} seconds."
                )
            elif tc.get('status') == 'success' or tc.get('status') == 'cached':
                text += "**Truecaller**\n"

                # Determine status
                if tc.get('is_spam'):
                    status = tc.get('spam_type', 'Spam')
                else:
                    status = 'Normal'
                text += f"Status: {status}\n"

                # Name
                if tc.get('name_not_available'):
                    text += "Name: Name is not yet available for this number\n"
                elif tc.get('name'):
                    text += f"Name: {tc.get('name')}\n"
                else:
                    text += "Name: -\n"

                # Telco/Carrier
                if tc.get('carrier'):
                    text += f"Telco: {tc.get('carrier')}"
                else:
                    text += "Telco: -"
            elif tc.get('status') == 'rate_limited':
                text += (
                    "**Truecaller**\n"
                    f"{tc.get('message', 'Rate limit reached')}"
                )
            elif tc.get('status') == 'skipped':
                text += (
                    "**Truecaller**\n"
                    f"{tc.get('message', 'Lookup skipped')}"
                )
            elif tc.get('status') == 'error':
                text += (
                    "**Truecaller**\n"
                    f"{tc.get('message', 'Check failed')}"
                )

        # Social Media ID Tracker
        st = context.user_data.get("social_tracker")
        if st:
            text += "\n\n———\n\n"
            text += "**Social Media ID Check**\n"
            if st.get('status') == 'success':
                text += f"Platform: {st.get('platform', '').title()}\n"
                text += f"Username: @{st.get('username', '-')}\n"
                text += f"Permanent ID: `{st.get('platform_user_id', '-')}`\n"
                if st.get('display_name'):
                    text += f"Display Name: {st.get('display_name')}\n"
            elif st.get('status') == 'not_found':
                text += "Account not found on this platform.\n"
            elif st.get('status') == 'no_session':
                text += f"{st.get('message', 'No session configured for this platform')}\n"
            elif st.get('status') == 'error':
                text += f"{st.get('message', 'Lookup failed')}\n"

        ucw = context.user_data.get("username_change_warning")
        if ucw:
            text += "\n⚠️ *USERNAME CHANGE DETECTED*\n"
            text += f"Previous: @{ucw[0]}\n"
            text += f"Current: @{ucw[1]}\n"

        await _safe_edit_message(
            context,
            chat_id,
            prompt_id,
            text=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu_from_search")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        return config.SEARCH_TERM

    context.user_data['search_results'] = all_results
    context.user_data['search_page'] = 0
    context.user_data['search_term'] = search_term

    
    await _safe_delete_message(context, chat_id, prompt_id)
    
    return await _send_search_result_page(update, context, new_message=True)


async def _send_search_result_page(update: Update, context: ContextTypes.DEFAULT_TYPE, new_message: bool = False) -> int:
    results = context.user_data.get('search_results', [])
    page = context.user_data.get('search_page', 0)
    search_term = context.user_data.get('search_term', '')
    
    total_results = len(results)
    if not results or page >= total_results:
        return ConversationHandler.END

    result_type, data = results[page]
    
    template_file = config.VERIFIED_CARD_TEMPLATE if result_type == "profile" else config.UNVERIFIED_CARD_TEMPLATE
    
    if result_type == "profile":
        profile_id = data["profile_id"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
              MAX(against_phone_number) AS against_phone_number,
              MAX(against_bank_number)  AS against_bank_number,
              MAX(against_social_url)   AS against_social_url,
              MAX(NULLIF(additional_info, '[]'))    AS additional_info
            FROM reports
            WHERE linked_profile_id = ?
        """, (profile_id,))
        row  = cursor.fetchone()
        conn.close()

        primary = {key: row[key] for key in row.keys()} if row else {}

        data = {
            **data,  # profile fields
            # fields for HTML
            "against_phone_number": primary.get("against_phone_number"),
            "against_bank_number": primary.get("against_bank_number"),
            "against_social_url": primary.get("against_social_url"),
            "additional_info": primary.get("additional_info"),
        }

    
    image_bytes = await generate_profile_image(template_file, data) # Guna dari image_generator
    
    if not image_bytes:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Error: Unable to generate image. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]]
            )
        )
        return ConversationHandler.END

    page_num = page + 1

    sem = context.user_data.get("semakmule")
    tc = context.user_data.get("truecaller")
    caption = f"Search result for `{search_term}`\n"

    if sem:
        caption += "\n**SemakMule Check Result**\n"
        if sem.get("ok"):
            caption += (
                f"• Search Count     : {sem.get('search_count', 0)}\n"
                f"• Police Reports   : {sem.get('police_reports', 0)}\n"
            )
        else:
            caption += (
                "• Unable to retrieve data from SemakMule at the moment.\n"
            )

    # Add Truecaller result
    if tc:
        caption += "\n**Truecaller**\n"

        if tc.get('status') == 'cooldown':
            caption += f"• API cooling down. Try again in {tc.get('cooldown_remaining', 0)}s.\n"
        elif tc.get('status') in ('success', 'cached'):
            # Determine status
            if tc.get('is_spam'):
                status = tc.get('spam_type', 'Spam')
            else:
                status = 'Normal'
            caption += f"• Status: {status}\n"

            # Name
            if tc.get('name_not_available'):
                caption += "• Name: Name is not yet available for this number\n"
            elif tc.get('name'):
                caption += f"• Name: {tc.get('name')}\n"
            else:
                caption += "• Name: -\n"

            # Telco/Carrier
            if tc.get('carrier'):
                caption += f"• Telco: {tc.get('carrier')}\n"
            else:
                caption += "• Telco: -\n"
        elif tc.get('status') == 'rate_limited':
            caption += f"• {tc.get('message', 'Rate limit reached')}\n"
        elif tc.get('status') == 'skipped':
            caption += f"• {tc.get('message', 'Lookup skipped')}\n"
        elif tc.get('status') == 'error':
            caption += f"• {tc.get('message', 'Check failed')}\n"

    # Social Media ID Tracker
    st = context.user_data.get("social_tracker")
    if st:
        caption += "\n**Social Media ID Check**\n"
        if st.get('status') == 'success':
            caption += f"• Platform: {st.get('platform', '').title()}\n"
            caption += f"• Username: @{st.get('username', '-')}\n"
            caption += f"• ID: `{st.get('platform_user_id', '-')}`\n"
            if st.get('display_name'):
                caption += f"• Name: {st.get('display_name')}\n"
        elif st.get('status') == 'not_found':
            caption += "• Account not found on this platform.\n"
        elif st.get('status') == 'no_session':
            caption += f"• {st.get('message', 'No session configured')}\n"
        elif st.get('status') == 'error':
            caption += f"• {st.get('message', 'Lookup failed')}\n"

    ucw = context.user_data.get("username_change_warning")
    if ucw:
        caption += "\n⚠️ *USERNAME CHANGE*\n"
        caption += f"• Previous: @{ucw[0]}\n"
        caption += f"• Current: @{ucw[1]}\n"

    caption += f"\n**Showing {page_num} of {total_results} result(s).**"
    
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(
            InlineKeyboardButton("⬅️", callback_data="search_prev")
        )
    
    pagination_buttons.append(
        InlineKeyboardButton(f"({page_num}/{total_results})", callback_data="search_nop")
    )
    
    if page < total_results - 1:
        pagination_buttons.append(
            InlineKeyboardButton("➡️", callback_data="search_next")
        )
        
    keyboard = []
    
    if total_results > 1:
        keyboard.append(pagination_buttons)
    
    if result_type == "profile":
        profile_id = data.get('profile_id')
        keyboard.append([
            InlineKeyboardButton("🏦 Bank Accounts", callback_data=f"list_banks_{profile_id}"),
            InlineKeyboardButton("📱 Phone Numbers", callback_data=f"list_phones_{profile_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("📖 Report List", callback_data=f"search_read_profile_{profile_id}")
        ])
    else:
        report_id = data.get('report_id')
        keyboard.append([
             InlineKeyboardButton("View Report", callback_data=f"search_read_report_{report_id}")
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu_from_search")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    chat_id = update.effective_chat.id
    
    if new_message:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_bytes,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        context.user_data['search_message_id'] = msg.message_id
    else:
        query = update.callback_query
        await query.answer()
        
        media = InputMediaPhoto(media=image_bytes, caption=caption, parse_mode=ParseMode.MARKDOWN)
        msg_id = context.user_data.get('search_message_id')
        
        try:
            await context.bot.edit_message_media(
                chat_id=chat_id,
                message_id=msg_id,
                media=media,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.warning(f"Carian: 'Next/Prev' gagal: {e}. Hantar baru.")
            await _safe_delete_message(context, chat_id, msg_id)
            return await _send_search_result_page(update, context, new_message=True)

    return config.SEARCH_RESULTS

async def search_change_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    
    page = context.user_data.get('search_page', 0)
    total_results = len(context.user_data.get('search_results', []))
    
    if query.data == "search_next" and page < total_results - 1:
        context.user_data['search_page'] = page + 1
    elif query.data == "search_prev" and page > 0:
        context.user_data['search_page'] = page - 1
    else:
        await query.answer("No more result.")
        return config.SEARCH_RESULTS
        
    return await _send_search_result_page(update, context, new_message=False)

async def search_read_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Union[int, None]:
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    action_type = data_parts[2]
    data_id = data_parts[3]
    
    conn = get_db_connection()
    text = ""
    
    try:
        cursor = conn.cursor()
        if action_type == "report":
            cursor.execute("SELECT * FROM reports WHERE report_id = ?", (data_id,))
            report = cursor.fetchone()
            
            if not report:
                text = "Error: Report not found."
                await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
                return None

            cursor.execute("SELECT file_path FROM screenshots WHERE report_id = ?", (data_id,))
            screenshots = [row['file_path'] for row in cursor.fetchall()]

            report_dict = {key: report[key] for key in report.keys()}
            report_dict['screenshots'] = screenshots

            text = _format_confirmation_message(report_dict) # Guna dari bot_utils
            text = text.replace("**STEP 8/8: Review & Submit**\n\nPlease verify that all entered information is correct before submission.\n\n", "")
            text = f"**Report View**\n\n" + text
            
            if screenshots:
                try:
                    media_group = [InputMediaPhoto(media=file_id) for file_id in screenshots]
                    await query.message.reply_media_group(media=media_group)
                except Exception as e:
                    logger.error(f"Gagal hantar album (search_read_details): {e}")
                    await query.message.reply_text("Error: Gagal memaparkan gambar bukti.")
            
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return None
                    
        elif action_type == "profile":
            search_msg_id = context.user_data.get('search_message_id')
            if search_msg_id:
                await _safe_delete_message(context, query.message.chat_id, search_msg_id)
            
            cursor.execute("SELECT main_identifier FROM profiles WHERE profile_id = ?", (data_id,))
            profile_row = cursor.fetchone()
            profile_name = profile_row['main_identifier'] if profile_row else data_id
            context.user_data['current_profile_name_for_list'] = profile_name

            cursor.execute(
                "SELECT report_id, title, submitted_at FROM reports WHERE linked_profile_id = ? ORDER BY submitted_at DESC", 
                (data_id,)
            )
            reports = cursor.fetchall()
            
            if not reports:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="No VERIFIED report found for this profile."
                )
                return await search_back_to_search_results(update, context, new_message=True)

            context.user_data['profile_reports_list'] = [{key: row[key] for key in row.keys()} for row in reports]
            context.user_data['profile_reports_page'] = 0
            context.user_data['current_profile_id_for_list'] = data_id
            
            return await _send_paginated_profile_reports_message(update, context, is_edit=False)
    
    except sqlite3.Error as e:
        logger.error(f"Error DB semasa 'search_read_details': {e}")
        text = "Error semasa mengambil data dari database."
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return None
    finally:
        conn.close()

async def _send_paginated_profile_reports_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_edit: bool = False) -> int:
    reports_list = context.user_data.get('profile_reports_list', [])
    page = context.user_data.get('profile_reports_page', 0)
    profile_id = context.user_data.get('current_profile_id_for_list', 'N/A')
    profile_name = context.user_data.get('current_profile_name_for_list', profile_id)
    
    REPORTS_PER_PAGE = 3
    total_reports = len(reports_list)
    total_pages = (total_reports + REPORTS_PER_PAGE - 1) // REPORTS_PER_PAGE
    
    start_index = page * REPORTS_PER_PAGE
    end_index = (page + 1) * REPORTS_PER_PAGE
    reports_to_show = reports_list[start_index:end_index]

    safe_profile_name = escape_markdown(profile_name, version=2)
    text = f"**Report List for {safe_profile_name}**\n\n"
    text += f"Page {page + 1} / {total_pages}"
    
    keyboard = []
    if not reports_to_show:
        text += "No report found."
    
    for report in reports_to_show:
        try:
            date_str = report['submitted_at']
            date = datetime.strptime(
                date_str, 
                '%Y-%m-%d %H:%M:%S.%f' if '.' in date_str else '%Y-%m-%d %H:%M:%S'
            ).strftime('%d-%m-%Y')
        except Exception:
            date = "N/A"
            
        button_text = f"{report['title']} ({date})"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"search_read_report_{report['report_id']}")
        ])

    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data="prof_report_prev"))
    else:
        pagination_buttons.append(InlineKeyboardButton(" ", callback_data="search_nop"))
        
    pagination_buttons.append(InlineKeyboardButton(f"({page + 1}/{total_pages})", callback_data="search_nop"))
    
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data="prof_report_next"))
    else:
        pagination_buttons.append(InlineKeyboardButton(" ", callback_data="search_nop"))
        
    if total_pages > 1:
        keyboard.append(pagination_buttons)
    
    keyboard.append([InlineKeyboardButton("⬅️ Back to Search Result", callback_data="back_to_search_results")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    chat_id = update.effective_chat.id
    
    if is_edit:
        prompt_id = context.user_data.get('profile_reports_message_id')
        await _safe_edit_message(context, chat_id, prompt_id, text=text, reply_markup=reply_markup)
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        context.user_data['profile_reports_message_id'] = msg.message_id

    return config.VIEW_PROFILE_REPORTS

async def search_change_profile_reports_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    
    page = context.user_data.get('profile_reports_page', 0)
    total_reports = len(context.user_data.get('profile_reports_list', []))
    REPORTS_PER_PAGE = 3
    total_pages = (total_reports + REPORTS_PER_PAGE - 1) // REPORTS_PER_PAGE
    
    if query.data == "prof_report_next" and page < total_pages - 1:
        context.user_data['profile_reports_page'] = page + 1
    elif query.data == "prof_report_prev" and page > 0:
        context.user_data['profile_reports_page'] = page - 1
    else:
        await query.answer("End of page.")
        return config.VIEW_PROFILE_REPORTS
    
    await query.answer()
    return await _send_paginated_profile_reports_message(update, context, is_edit=True)

async def search_back_to_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, new_message: bool = False) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    
    prompt_id = context.user_data.pop('profile_reports_message_id', None)
    if prompt_id:
        await _safe_delete_message(context, update.effective_chat.id, prompt_id)
    
    context.user_data.pop('profile_reports_list', None)
    context.user_data.pop('profile_reports_page', None)
    context.user_data.pop('current_profile_id_for_list', None)
    context.user_data.pop('current_profile_name_for_list', None)
    
    return await _send_search_result_page(update, context, new_message=True)

async def search_cancel_and_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop('in_search_mode', None)
    
    msg_id = context.user_data.get('search_message_id')
    if msg_id:
        await _safe_delete_message(context, query.message.chat_id, msg_id)
    
    prompt_id = context.user_data.pop('profile_reports_message_id', None)
    if prompt_id:
        await _safe_delete_message(context, update.effective_chat.id, prompt_id)
        
    context.user_data.clear()
    
    await start(update, context) # Guna dari handlers_general
    return ConversationHandler.END

def parse_additional_info(additional_info: str) -> List[str]:
    """
    Safely parse additional_info JSON string into list.
    """
    if not additional_info or additional_info == '[]':
        return []

    try:
        data = json.loads(additional_info)
        if isinstance(data, list):
            return [str(x).strip() for x in data]
    except Exception:
        pass

    return []

def extract_banks_from_additional_info(additional_info: str) -> List[Dict[str, str]]:
    results = []

    for item in parse_additional_info(additional_info):
        if not item.startswith("Bank:"):
            continue

        payload = item.replace("Bank:", "", 1).strip()
        parts = [p.strip() for p in payload.split(",")]

        if len(parts) < 2:
            continue  # invalid / corrupted entry

        results.append({
            "account_number": parts[0],
            "bank_name": parts[1] if len(parts) > 1 else None,
            "holder_name": parts[2] if len(parts) > 2 else None,
        })

    return results

def extract_phones_from_additional_info(additional_info: str) -> List[str]:
    phones = []

    for item in parse_additional_info(additional_info):
        if not item.startswith("Telefon:"):
            continue

        phone = item.replace("Telefon:", "", 1).strip()
        phones.append(phone)

    return phones


async def list_banks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    profile_id = query.data.split('_')[-1]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # === NORMALIZED ===
        cursor.execute("""
            SELECT account_number, bank_name, holder_name, report_count
            FROM profile_bank_accounts
            WHERE profile_id = ?
            ORDER BY report_count DESC
        """, (profile_id,))
        normalized = cursor.fetchall()

        normalized_map = {
            row["account_number"]: row for row in normalized
        }

        # === FROM additional_info ===
        cursor.execute("""
            SELECT additional_info
            FROM reports
            WHERE linked_profile_id = ?
              AND additional_info IS NOT NULL
              AND additional_info != '[]'
        """, (profile_id,))

        extracted = []

        for row in cursor.fetchall():
            extracted.extend(
                extract_banks_from_additional_info(row["additional_info"])
            )

        # deduplicate
        extracted = [
            b for b in extracted
            if b["account_number"] not in normalized_map
        ]

        if not normalized and not extracted:
            await query.message.reply_text("No bank account record found for this profile.")
            return

        text = "**Related bank account(s)**\n"

        idx = 1
        for row in normalized:
            text += (
                f"**{idx}. `{row['account_number']}`**\n"
                f"   - Holder Name: `{row['holder_name']}`\n"
                f"   - Bank Name: `{row['bank_name']}`\n"
                f"   - Total Reports: {row['report_count']}\n\n"
            )
            idx += 1

        for b in extracted:
            text += (
                f"**{idx}. `{b['account_number']}`**\n"
                f"   - Holder Name: `{b.get('holder_name', '-')}`\n"
                f"   - Bank Name: `{b.get('bank_name', '-')}`\n\n"
            )
            idx += 1

        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    finally:
        conn.close()


async def list_phones_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    profile_id = query.data.split('_')[-1]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT phone_number, report_count
            FROM profile_phone_numbers
            WHERE profile_id = ?
            ORDER BY report_count DESC
        """, (profile_id,))
        normalized = cursor.fetchall()

        normalized_set = {row["phone_number"] for row in normalized}

        cursor.execute("""
            SELECT additional_info
            FROM reports
            WHERE linked_profile_id = ?
              AND additional_info IS NOT NULL
              AND additional_info != '[]'
        """, (profile_id,))

        extracted = []
        for row in cursor.fetchall():
            extracted.extend(
                extract_phones_from_additional_info(row["additional_info"])
            )

        extracted = [p for p in extracted if p not in normalized_set]

        if not normalized and not extracted:
            await query.message.reply_text("No phone number record found for this profile.")
            return

        text = "**Related phone number(s)**\n"

        idx = 1
        for row in normalized:
            text += (
                f"**{idx}. `{row['phone_number']}`**\n"
                f"   - Total Reports: {row['report_count']}\n\n"
            )
            idx += 1

        for phone in extracted:
            text += (
                f"**{idx}. `{phone}`**\n\n"
            )
            idx += 1

        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    finally:
        conn.close()


async def search_qr_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # QR hanya aktif dalam search mode
    if not context.user_data.get('in_search_mode'):
        return

    logger.info("QR image received in search mode")

    try:
        await update.message.delete()
    except Exception:
        pass

    chat_id = update.effective_chat.id
    prompt_id = context.user_data.get('prompt_message_id')

    # Ambil gambar
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()

    from qr_utils import decode_qr_image
    from duitnow_parser import parse_duitnow_qr

    qr_payload = decode_qr_image(image_bytes)
    if not qr_payload:
        await _safe_edit_message(
            context,
            chat_id,
            prompt_id,
            text="❌ The QR code could not be read. Please make sure the image is clear.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu_from_search")]]
            )
        )
        return config.SEARCH_TERM

    parsed = parse_duitnow_qr(qr_payload)

    merchant = parsed.get("merchant_name")
    identifier = parsed.get("identifier")
    bank_name = parsed.get("bank_name")



    text = "**Extracted information from QR**\n\n"

    text += f"Holder Name: `{merchant}`\n" if merchant else "Holder Name: Not found\n"
    text += f"Bank Name: `{bank_name}`\n" if bank_name else "Bank Name: Not Found\n"
    text += f"Identifier: `{identifier}`\n" if identifier else "Identifier: Not Found\n"
    text += "\n\n_An identifier can be a bank account number, security ID, or phone number. Just copy one of the details above and send it to start searching._"



    # === EDIT MESSAGE MOD CARIAN, INLINE KEYBOARD KEKAL ===
    await _safe_edit_message(
        context,
        chat_id,
        prompt_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu_from_search")]]
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    return config.SEARCH_TERM
