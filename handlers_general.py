# handlers_general.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ChatMemberStatus
from telegram.constants import ParseMode
from typing import Union
import config
from config import ADMIN_USER_IDS
from bot_utils import _safe_edit_message, _safe_delete_message, send_report_notification
from datetime import datetime
from database import get_db_connection
from playwright.async_api import async_playwright
import tempfile
import os

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id

    # Clear any active conversation state
    context.user_data.clear()
    logger.info(f"{user_id} started/restarted the bot - clearing conversation state")

    if user:
        register_user(user)
        conn = get_db_connection()
        cursor = conn.cursor()

        touch_user_activity(cursor, user_id)
        conn.commit()
        conn.close()

    if not await ensure_user_joined(update, context):
        return ConversationHandler.END

    # === 1) HANTAR STATISTIC IMAGE (TANPA CAPTION) ===
    #stats = get_system_statistics()
    #html = build_statistic_html(stats)
    #image_path = await render_html_to_image(html)

    #with open(image_path, "rb") as img:
    #    await context.bot.send_photo(
    #        chat_id=chat_id,
    #        photo=img
    #    )

    # === 2) WELCOME MESSAGE SEBAGAI TEXT ===
    text = (
        "Welcome to PenipuMY V2\n\n"
        "This bot helps you check, identify, and report individuals or accounts "
        "suspected of being involved in scams.\n\n"
        "🔍 *Search*\n"
        "Check scam records using bank account numbers, names, phone numbers, "
        "DuitNow QR codes, or social media accounts.\n\n"
        "➕ *Submit a Report*\n"
        "Report scam cases to spread awareness and help protect others."

    )

    keyboard = [
        [
            InlineKeyboardButton("🔍 Search", callback_data="main_search"),
            InlineKeyboardButton("➕ Report", callback_data="main_report"),
        ],
        [
            InlineKeyboardButton("📊 Statistics", callback_data="main_statistics"),
            InlineKeyboardButton("🌐 Web Version", url="https://penipu.my"),
        ]
    ]

    if user_id in ADMIN_USER_IDS:
        logger.info(f"Admin (ID: {user_id}) telah memulakan bot.")
        keyboard.append(
            [InlineKeyboardButton("🛡️ Admin Panel", callback_data="admin_menu")]
        )
    else:
        logger.info(f"{user_id} started the bot.")
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    # === 3) HANTAR TEXT (INI YANG AKAN DIEDIT LEPAS NI) ===
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    elif update.callback_query:
        query = update.callback_query
        await query.answer()

        success = await _safe_edit_message(
            context,
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        if not success:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

    # Return END to properly terminate any active conversation
    return ConversationHandler.END
            
  
def touch_user_activity(cursor, user_id):
    cursor.execute("""
        UPDATE users
        SET last_active_datetime = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (user_id,))


def register_user(tg_user):

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (
                user_id,
                username,
                first_name,
                last_name,
                created_date,
                last_active_datetime
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(tg_user.id),
                tg_user.username,
                tg_user.first_name,
                tg_user.last_name,
                datetime.now(),
                datetime.now()
            )
        )
        conn.commit()
    finally:
        conn.close()


def get_system_statistics():
    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}

    # =====================
    # USERS STATS
    # =====================

    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    stats["total_users"] = cursor.fetchone()[0]

    # New users today
    cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE date(created_date) = date('now')
    """)
    stats["new_users_today"] = cursor.fetchone()[0]

    # New users yesterday
    cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE date(created_date) = date('now','-1 day')
    """)
    stats["new_users_yesterday"] = cursor.fetchone()[0]

    # Active Base (last 30 days, bot interaction based)
    cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE last_active_datetime >= datetime('now','-30 day')
    """)
    stats["active_users_30d"] = cursor.fetchone()[0]

    # Active Base %
    cursor.execute("""
        SELECT ROUND(
            SUM(last_active_datetime >= datetime('now','-30 day')) * 100.0 / COUNT(*),
            1
        )
        FROM users
    """)
    stats["active_base_percent"] = cursor.fetchone()[0]

    # =====================
    # REPORTS STATS
    # =====================

    # Total reports
    cursor.execute("SELECT COUNT(*) FROM reports")
    stats["total_reports"] = cursor.fetchone()[0]

    # =====================
    # BANK / PHONE / SOCIAL
    # =====================

    splitter_cte = """
        WITH RECURSIVE split(part, rest) AS (
          SELECT '',
                 TRIM(REPLACE(REPLACE(REPLACE(additional_info,'[',''),']',''),'"',''))
          FROM reports
          WHERE additional_info IS NOT NULL
            AND additional_info != '[]'

          UNION ALL

          SELECT
            TRIM(
              CASE
                WHEN instr(rest, ', ') > 0
                THEN substr(rest,1,instr(rest,', ')-1)
                ELSE rest
              END
            ),
            CASE
              WHEN instr(rest, ', ') > 0
              THEN substr(rest,instr(rest,', ')+2)
              ELSE ''
            END
          FROM split
          WHERE rest != ''
        )
    """

    # Total bank accounts
    cursor.execute(splitter_cte + """
        SELECT COUNT(DISTINCT bank) FROM (
          SELECT TRIM(substr(part, instr(part,'Bank:')+5)) AS bank
          FROM split
          WHERE part LIKE 'Bank:%'

          UNION ALL

          SELECT TRIM(against_bank_number)
          FROM reports
          WHERE against_bank_number IS NOT NULL
            AND against_bank_number != ''
        )
    """)
    stats["total_banks"] = cursor.fetchone()[0]

    # Total phone numbers
    cursor.execute(splitter_cte + """
        SELECT COUNT(DISTINCT phone) FROM (
          SELECT TRIM(substr(part, instr(part,'Telefon:')+8)) AS phone
          FROM split
          WHERE part LIKE 'Telefon:%'

          UNION ALL

          SELECT TRIM(against_phone_number)
          FROM reports
          WHERE against_phone_number IS NOT NULL
            AND against_phone_number != ''
        )
    """)
    stats["total_phones"] = cursor.fetchone()[0]

    # Total social media
    cursor.execute(splitter_cte + """
        SELECT COUNT(DISTINCT social) FROM (
          SELECT
            rtrim(
              replace(
                substr(part, instr(part,'Sosial:')+7),
                'www.',
                ''
              ),
              '/'
            ) AS social
          FROM split
          WHERE part LIKE 'Sosial:%'

          UNION ALL

          SELECT
            rtrim(
              replace(against_social_url,'www.',''),
              '/'
            )
          FROM reports
          WHERE against_social_url IS NOT NULL
            AND against_social_url != ''
        )
    """)
    stats["total_socials"] = cursor.fetchone()[0]

    # =====================
    # LOSSES
    # =====================

    # Cumulative verified losses
    cursor.execute("""
        SELECT COALESCE(SUM(amount_scammed),0)
        FROM reports
        WHERE report_status = 'VERIFIED'
    """)
    stats["total_verified_loss"] = cursor.fetchone()[0]

    # Highest single loss
    cursor.execute("""
        SELECT COALESCE(MAX(amount_scammed),0)
        FROM reports
        WHERE report_status = 'VERIFIED'
    """)
    stats["highest_single_loss"] = cursor.fetchone()[0]

    # =====================
    # TRUECALLER CACHE COUNT
    # =====================
    try:
        cursor.execute("SELECT COUNT(*) FROM truecaller_cache")
        stats["tc_cache_count"] = cursor.fetchone()[0]
    except Exception:
        stats["tc_cache_count"] = 0

    conn.close()

    # =====================
    # API STATUS (Demo Mode)
    # =====================
    stats["tc_status"] = "Demo Mode"
    stats["tc_status_color"] = "#6b7280"
    stats["sm_status"] = "Demo Mode"
    stats["sm_status_color"] = "#6b7280"

    return stats


async def render_html_to_image(html: str) -> str:
    tmp_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    tmp_html.write(html.encode("utf-8"))
    tmp_html.close()

    output_png = tmp_html.name.replace(".html", ".png")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 920, "height": 520}
        )
        await page.goto(f"file:///{tmp_html.name}")
        await page.wait_for_timeout(300)
        await page.screenshot(path=output_png, full_page=True)
        await browser.close()

    os.unlink(tmp_html.name)
    return output_png

def build_statistic_html(stats: dict) -> str:
    template_path = os.path.join(TEMPLATE_DIR, "modern_stats.html")

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    return (
        html
        # ===== USERS =====
        .replace("{{ stats.total_users }}", f"{stats['total_users']:,}")
        .replace("{{ stats.new_users_today }}", f"{stats['new_users_today']:,}")
        .replace("{{ stats.new_users_yesterday }}", f"{stats['new_users_yesterday']:,}")
        .replace("{{ stats.active_base_percent }}", f"{stats['active_base_percent']}")

        # ===== REPORTS / DATABASE =====
        .replace("{{ stats.total_reports }}", f"{stats['total_reports']:,}")
        .replace("{{ stats.total_banks }}", f"{stats['total_banks']:,}")
        .replace("{{ stats.total_phones }}", f"{stats['total_phones']:,}")
        .replace("{{ stats.total_socials }}", f"{stats['total_socials']:,}")

        # ===== LOSSES =====
        .replace("{{ stats.total_verified_loss }}", f"{stats['total_verified_loss']:,.2f}")
        .replace("{{ stats.highest_single_loss }}", f"{stats['highest_single_loss']:,.2f}")

        # ===== API STATUS =====
        .replace("{{ stats.tc_status_color }}", stats['tc_status_color'])
        .replace("{{ stats.tc_status }}", stats['tc_status'])
        .replace("{{ stats.sm_status_color }}", stats['sm_status_color'])
        .replace("{{ stats.sm_status }}", stats['sm_status'])
        .replace("{{ stats.tc_cache_count }}", f"{stats['tc_cache_count']:,}")
    )


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    user_id = query.from_user.id

    logger.info(f"{user_id} get statistics.")
    
    # === TRACK ACTIVITY ===
    conn = get_db_connection()
    cursor = conn.cursor()
    touch_user_activity(cursor, user_id)
    conn.commit()
    conn.close()

    # === 1) DELETE CURRENT MESSAGE ===
    try:
        await query.message.delete()
    except Exception:
        pass  # kalau gagal, ignore

    # === 2) GENERATE + SEND STAT IMAGE ===
    stats = get_system_statistics()
    html = build_statistic_html(stats)
    image_path = await render_html_to_image(html)

    with open(image_path, "rb") as img:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=img
        )

    # === 3) SEND START MESSAGE FRESH ===
    await start(update, context)


async def ensure_user_joined(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id

    try:
        member = await context.bot.get_chat_member(
            chat_id=config.REQUIRED_CHANNEL_ID,
            user_id=user_id
        )

        if member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ):
            return True

    except Exception as e:
        logger.warning(f"Join check failed for user {user_id}: {e}")

    # ❌ BELUM JOIN
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=config.REQUIRED_CHANNEL_URL)],
        [InlineKeyboardButton("🔄 Refresh", callback_data="recheck_join")]
    ])

    text = (
        "🚫 **Access Restricted**\n\n"
        "You must **join the official channel** before using this bot."
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )

    return False

async def recheck_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if await ensure_user_joined(update, context):
        return await start(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Batalkan mana-mana 'conversation'."""
    text = "Process aborted."
    
    # Padam mesej 'prompt' screenshot jika ada (ini logik paling rumit)
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    
    last_reply_id = context.user_data.pop('last_screenshot_reply_id', None)
    if last_reply_id:
        await _safe_delete_message(context, chat_id, last_reply_id)
    
    prompt_id = context.user_data.pop('screenshot_prompt_id', None)
    if prompt_id:
        await _safe_delete_message(context, chat_id, prompt_id)
    # --- Tamat logik screenshot ---

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.edit_message_text(text)
        except Exception as e:
            logger.warning(f"Gagal edit mesej batal: {e}")
            await context.bot.send_message(chat_id=chat_id, text=text)
    
    context.user_data.clear()
    #logger.info("Data laporan/carian/admin sementara telah dipadam (Batal).")
    logger.info(f"{user_id} clicked cancel.")

    await start(update, context)
    return ConversationHandler.END


async def auto_archive_needs_info(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback: auto-archive NEEDS_INFO reports older than 30 days."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT report_id, submitter_user_id
            FROM reports
            WHERE report_status = 'NEEDS_INFO'
              AND needs_info_since <= datetime('now', '-30 days')
        """)
        expired_reports = cursor.fetchall()

        if not expired_reports:
            return

        for row in expired_reports:
            report_id = row['report_id']
            reporter_id = row['submitter_user_id']

            cursor.execute("""
                UPDATE reports
                SET report_status = 'REJECTED',
                    auto_rejected = 1,
                    rejection_reason = 'Auto-archived: no response within 30 days'
                WHERE report_id = ?
            """, (report_id,))

            # Notify reporter
            try:
                await send_report_notification(
                    context.bot, reporter_id, report_id, 'auto_archived'
                )
            except Exception as e:
                logger.warning(f"Failed to notify reporter {reporter_id} for auto-archived report {report_id}: {e}")

        conn.commit()
        logger.info(f"Auto-archived {len(expired_reports)} NEEDS_INFO report(s)")

    except Exception as e:
        logger.error(f"Error in auto_archive_needs_info: {e}")
    finally:
        conn.close()