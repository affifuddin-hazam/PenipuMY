# handlers_admin.py
import logging
import json
import re
import sqlite3
import uuid
import asyncio
from datetime import datetime
from typing import Union
from unittest.mock import Mock
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    InputMediaPhoto, Message, CallbackQuery
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Import dari fail lain
import config
from database import get_db_connection
from bot_utils import _safe_edit_message, _safe_delete_message, _format_confirmation_message
from handlers_general import start # Perlu untuk 'cancel' & 'start'

logger = logging.getLogger(__name__)

# === Salin SEMUA fungsi dari Bahagian 7 (Admin) ke sini ===
# (admin_start, _get_next_unverified_report, admin_review_next_report, ...
# ... admin_verify_start, _run_aggregation_in_db, admin_link_profile, ...
# ... admin_get_new_profile_name, dll.)

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in config.ADMIN_USER_IDS:
        await query.message.reply_text("Access denied. You do not have permission to perform this action.")
        return ConversationHandler.END
        
    text = (
        "**🛡️ Admin Panel**\n\n"
        "Please select from the menu below:"
    )
    keyboard = [
        [InlineKeyboardButton("Verify Reports", callback_data="admin_review_next")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")],
    ]
    
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return config.ADMIN_MENU

async def _get_next_unverified_report(context):
    skipped = context.user_data.get("skipped_reports", set())

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM reports
            WHERE report_status = 'UNVERIFIED'
            ORDER BY submitted_at ASC
        """)
        rows = cursor.fetchall()

        for row in rows:
            if row["report_id"] in skipped:
                continue

            cursor.execute(
                "SELECT file_path FROM screenshots WHERE report_id = ?",
                (row["report_id"],)
            )
            screenshots = [r["file_path"] for r in cursor.fetchall()]

            return dict(row), screenshots

        # Semua UNVERIFIED dah diskip dalam session
        context.user_data["skipped_reports"] = set()
        return None, None

    except sqlite3.Error as e:
        logger.error(f"DB error in _get_next_unverified_report: {e}")
        return None, None

    finally:
        conn.close()

async def admin_review_next_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    
    await _safe_delete_message(context, chat_id, query.message.message_id)

    report_data, screenshots = await _get_next_unverified_report(context)
    
    if not report_data:
        await context.bot.send_message(
            chat_id=chat_id,
            text="All reports has been verified."
        )
        await start(update, context) # Guna dari handlers_general
        return ConversationHandler.END

    report_data['screenshots'] = [s for s in screenshots]

    report_id = report_data['report_id']
    context.user_data['admin_current_report_id'] = report_id
    context.user_data['admin_current_report_data'] = report_data
    
    text = _format_confirmation_message(report_data) # Guna dari bot_utils
    text = f"**Report ID: {report_id}**\n" + text.replace(
        "**STEP 8/8: Review & Submit**\n\nPlease verify that all entered information is correct before submission.", ""
    )
    
    if screenshots:
        try:
            media_group = [InputMediaPhoto(media=file_id) for file_id in screenshots]
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
        except Exception as e:
            logger.error(f"Admin Gagal hantar album: {e}")
            await context.bot.send_message(chat_id=chat_id, text="Ralat: Gagal memaparkan gambar bukti.")

    keyboard = [
        [
            InlineKeyboardButton("✅ Verify", callback_data="admin_verify"),
            InlineKeyboardButton("❌ Dispute", callback_data="admin_dispute"),
        ],
        [
            InlineKeyboardButton("📝 Needs Info", callback_data="admin_needs_info"),
            InlineKeyboardButton("⏭️ Skip", callback_data="admin_skip"),
        ],
        [InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_menu_back")]
    ]
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['prompt_message_id'] = msg.message_id

    return config.ADMIN_REVIEW_REPORT

async def admin_update_report_status(update: Update, context: ContextTypes.DEFAULT_TYPE, new_status: str) -> int:
    query = update.callback_query
    await query.answer()
    
    report_id = context.user_data.get('admin_current_report_id')
    
    if new_status == "SKIP":
        skipped = context.user_data.setdefault("skipped_reports", set())
        skipped.add(report_id)

        context.user_data.pop("admin_current_report_id", None)
        context.user_data.pop("admin_current_report_data", None)

        return await admin_review_next_report(update, context)

    if not report_id:
        await query.message.reply_text("Ralat: Sesi admin tamat. Sila mula semula dari /start.")
        return ConversationHandler.END
        
    report_data = context.user_data.get('admin_current_report_data')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reports SET report_status = ? WHERE report_id = ?",
            (new_status, report_id)
        )
        conn.commit()
        logger.info(f"Admin menukar status Laporan ID: {report_id} kepada {new_status}")
    except sqlite3.Error as e:
        logger.error(f"Ralat DB semasa 'dispute' laporan: {e}")
    finally:
        conn.close()

    # Send notification to reporter
    if new_status == "DISPUTED" and report_data:
        reporter_user_id = report_data.get('submitter_user_id')
        if reporter_user_id:
            from bot_utils import send_report_notification
            await send_report_notification(
                bot=context.bot,
                reporter_user_id=reporter_user_id,
                report_id=report_id,
                notification_type='disputed'
            )

    context.user_data.pop('admin_current_report_id', None)
    context.user_data.pop('admin_current_report_data', None)

    return await admin_review_next_report(update, context)

async def admin_skip_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await admin_update_report_status(update, context, "SKIP")

async def admin_dispute_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await admin_update_report_status(update, context, "DISPUTED")

async def admin_verify_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    report_data = context.user_data.get('admin_current_report_data')
    if not report_data:
        await query.message.reply_text("Ralat: Sesi admin tamat. Sila mula semula dari /start.")
        return ConversationHandler.END

    report_id = report_data['report_id']
    report_type = report_data['report_against_type']
    
    search_key = None
    search_value = None
    search_table = None
    
    if report_type == "PHONE":
        search_key = "phone_number"
        search_value = report_data.get('against_phone_number')
        search_table = "profile_phone_numbers"
    elif report_type == "BANK":
        search_key = "account_number"
        search_value = report_data.get('against_bank_number')
        search_table = "profile_bank_accounts"
    elif report_type == "SOCIAL":
        search_key = "url"
        search_value = report_data.get('against_social_url')
        search_table = "profile_social_media"

    if not search_value:
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            "Ralat: Laporan ini tiada data utama. Sila 'Tolak' atau 'Langkau'.",
            reply_markup=query.message.reply_markup
        )
        return config.ADMIN_REVIEW_REPORT

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query_sql = f"""
        SELECT p.profile_id, p.main_identifier
        FROM profiles p
        JOIN {search_table} t ON p.profile_id = t.profile_id
        WHERE t.{search_key} = ?
        """
        cursor.execute(query_sql, (search_value,))
        existing_profiles = cursor.fetchall()
        
    except sqlite3.Error as e:
        logger.error(f"Ralat DB semasa semak pautan admin: {e}")
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            f"Ralat DB: {e}", reply_markup=query.message.reply_markup
        )
        return config.ADMIN_REVIEW_REPORT
    finally:
        conn.close()

    if existing_profiles:
        logger.info(f"Semakan Laporan ID {report_id}: Menjumpai {len(existing_profiles)} profil sedia ada.")
        
        text = (
            f"**Report ID: {report_id}**\n\n"
            f"Info `{search_key}: {search_value}` "
            "telah dikesan dalam profil-profil berikut:\n\n"
        )
        keyboard = []
        for profile in existing_profiles:
            profile_id = profile['profile_id']
            profile_name = profile['main_identifier']
            text += f"- `{profile_name}` (ID: `{profile_id}`)\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"🔗 Pautkan ke '{profile_name}'", 
                    callback_data=f"admin_link_{profile_id}"
                )
            ])
            
        text += "\nSila pilih profil untuk dipautkan, atau cipta profil baru."
        keyboard.append(
            [InlineKeyboardButton("🆕 Cipta Profil Baru", callback_data="admin_link_new")]
        )
        keyboard.append(
            [InlineKeyboardButton("⬅️ Kembali (Batal Sahkan)", callback_data="admin_back_to_review")]
        )
        
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text=text, reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return config.ADMIN_LINK_PROFILE

    else:
        logger.info(f"Semakan Laporan ID {report_id}: Tiada profil ditemui. Perlu cipta baru.")
        
        text = (
            f"**Semakan Laporan ID: {report_id}**\n\n"
            "Tiada profil sedia ada dijumpai untuk maklumat ini.\n\n"
            "Sila masukkan **Nama Utama** (Main Identifier) untuk profil baru ini.\n"
            "(Contoh: Alex GTR, Geng Jual Kereta)"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Kembali (Batal Sahkan)", callback_data="admin_back_to_review")]
        ]
        
        msg = await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text=text, reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        if msg:
            context.user_data['prompt_message_id'] = msg.message_id
        
        return config.ADMIN_NEW_PROFILE_NAME

async def admin_back_to_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await _safe_delete_message(context, query.message.chat_id, query.message.message_id)
    return await admin_review_next_report(update, context)


def _run_aggregation_in_db(report_data: dict, profile_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    report_id = report_data['report_id']
    amount = report_data.get('amount_scammed', 0)
    report_type = report_data['report_against_type']
    additional_evidence = report_data.get("additional_info")
    logging.info("report additional_info: %s", additional_evidence)


    try:
        cursor.execute("BEGIN TRANSACTION")
        
        cursor.execute(
            "UPDATE reports SET report_status = 'VERIFIED', linked_profile_id = ? WHERE report_id = ?",
            (profile_id, report_id)
        )
        
        cursor.execute(
            """
            UPDATE profiles 
            SET 
                stat_total_loss = stat_total_loss + ?,
                stat_total_reports = stat_total_reports + 1,
                updated_at = ?
            WHERE profile_id = ?
            """,
            (amount, datetime.now(), profile_id)
        )
        
        if report_type == "PHONE":
            phone_num = report_data.get('against_phone_number')
            if phone_num:
                cursor.execute(
                    """
                    INSERT INTO profile_phone_numbers (profile_id, phone_number, report_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(profile_id, phone_number) DO UPDATE SET
                        report_count = report_count + 1
                    """,
                    (profile_id, phone_num)
                )
        
        elif report_type == "BANK":
            bank_num = report_data.get('against_bank_number')
            if bank_num:
                cursor.execute(
                    """
                    INSERT INTO profile_bank_accounts 
                        (profile_id, account_number, bank_name, holder_name, report_count)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(profile_id, account_number) DO UPDATE SET
                        report_count = report_count + 1,
                        holder_name = excluded.holder_name,
                        bank_name = excluded.bank_name
                    """,
                    (
                        profile_id, 
                        bank_num,
                        report_data.get('against_bank_name'),
                        report_data.get('against_bank_holder_name')
                    )
                )

        elif report_type == "SOCIAL":
            url = report_data.get('against_social_url')
            if url:
                cursor.execute(
                    """
                    INSERT INTO profile_social_media (profile_id, url, report_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(profile_id, url) DO UPDATE SET
                        report_count = report_count + 1
                    """,
                    (profile_id, url)
                )
        
        if additional_evidence:
            try:
                evidence_list = json.loads(additional_evidence)
                logging.info(evidence_list)
            except Exception:
                evidence_list = []

            for item in evidence_list:
                if not isinstance(item, str):
                    continue

                text = item.lower()

                if "telefon" in text:
                    # extract nombor telefon
                    match = re.search(r'(\+?\d{8,15})', item)
                    if not match:
                        continue

                    phone = match.group(1)

                    cursor.execute(
                        """
                        INSERT INTO profile_phone_numbers (profile_id, phone_number, report_count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(profile_id, phone_number)
                        DO UPDATE SET report_count = report_count + 1
                        """,
                        (profile_id, phone)
                    )
        
        cursor.execute(
            "UPDATE profiles SET stat_unique_banks = (SELECT COUNT(*) FROM profile_bank_accounts WHERE profile_id = ?) WHERE profile_id = ?",
            (profile_id, profile_id)
        )
        cursor.execute(
            "UPDATE profiles SET stat_unique_phones = (SELECT COUNT(*) FROM profile_phone_numbers WHERE profile_id = ?) WHERE profile_id = ?",
            (profile_id, profile_id)
        )
        cursor.execute(
            "UPDATE profiles SET stat_unique_socials = (SELECT COUNT(*) FROM profile_social_media WHERE profile_id = ?) WHERE profile_id = ?",
            (profile_id, profile_id)
        )
        
        conn.commit()
        logger.info(f"AGREGASI BERJAYA: Laporan ID {report_id} dipautkan ke Profil ID {profile_id}")
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"AGREGASI GAGAL: Ralat DB untuk Laporan ID {report_id}: {e}")
        raise
    finally:
        conn.close()


async def admin_link_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Memautkan...")
    
    profile_id = query.data.split('_')[-1]
    report_data = context.user_data.get('admin_current_report_data')
    
    if not report_data or not profile_id:
        await query.edit_message_text("Ralat: Sesi admin tamat. Sila mula semula.")
        return ConversationHandler.END
        
    try:
        _run_aggregation_in_db(report_data, profile_id)

        text = (
            f"✅ Berjaya! Laporan ID `{report_data['report_id']}` telah dipautkan "
            f"ke profil `{profile_id}`."
        )
        success = await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text=text, reply_markup=None, parse_mode=ParseMode.MARKDOWN
        )
        if not success:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=text, parse_mode=ParseMode.MARKDOWN
            )

        # Notify reporter
        reporter_user_id = report_data.get('submitter_user_id')
        if reporter_user_id:
            from bot_utils import send_report_notification
            await send_report_notification(
                bot=context.bot,
                reporter_user_id=reporter_user_id,
                report_id=report_data['report_id'],
                notification_type='verified'
            )

    except Exception as e:
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text=f"Gagal memautkan laporan: {e}",
            reply_markup=None
        )

    context.user_data.clear()
    await context.bot.send_message(chat_id=query.message.chat_id, text="Memuatkan menu admin...")
    return await admin_start(update, context)


async def admin_ask_new_profile_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    logger.info(f"Admin memulakan ciptaan profil baru untuk Laporan ID: {context.user_data.get('admin_current_report_id')}")
    
    text = (
        f"**Semakan Laporan ID: {context.user_data.get('admin_current_report_id')}**\n\n"
        "Sila masukkan **Nama Utama** (Main Identifier) untuk profil baru ini.\n"
        "(Contoh: Alex GTR, Geng Jual Kereta)"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali (Batal Sahkan)", callback_data="admin_back_to_review")]
    ]
    
    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id
    
    return config.ADMIN_NEW_PROFILE_NAME


async def admin_get_new_profile_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Padam mesej input admin
    try:
        await update.message.delete()
    except Exception:
        pass

    profile_name = update.message.text.strip()
    report_data = context.user_data.get('admin_current_report_data')
    chat_id = update.effective_chat.id

    if not report_data:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Sesi admin tamat. Sila mula semula."
        )
        return ConversationHandler.END

    profile_id = f"pid-{uuid.uuid4().hex[:8]}"

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Cipta profil
        cursor.execute(
            """
            INSERT INTO profiles (profile_id, main_identifier, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (profile_id, profile_name, datetime.now(), datetime.now())
        )
        conn.commit()

        logger.info(f"Profil baru dicipta: {profile_name} (ID: {profile_id})")

        # Jalankan agregasi
        _run_aggregation_in_db(report_data, profile_id)

        # HANTAR mesej baru (JANGAN edit)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ **Berjaya!**\n\n"
                f"Profil baru **{profile_name}** telah dicipta.\n"
                f"Laporan ID `{report_data['report_id']}` telah dipautkan."
            ),
            parse_mode=ParseMode.MARKDOWN
        )

        # Notify reporter
        reporter_user_id = report_data.get('submitter_user_id')
        if reporter_user_id:
            from bot_utils import send_report_notification
            await send_report_notification(
                bot=context.bot,
                reporter_user_id=reporter_user_id,
                report_id=report_data['report_id'],
                notification_type='verified'
            )

    except Exception as e:
        logger.error(f"Gagal cipta profil baru / agregasi: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Gagal mencipta profil: {e}"
        )
        return ConversationHandler.END

    finally:
        conn.close()

    # RESET STATE
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("➡️ Semak Laporan Seterusnya", callback_data="admin_review_next")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text="🛡️ Panel Admin\n\nSila pilih tugasan:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return config.ADMIN_MENU


# === NEEDS INFO HANDLERS ===

async def admin_needs_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin clicks 'Needs Info' — prompt for optional reason."""
    query = update.callback_query
    await query.answer()

    report_id = context.user_data.get('admin_current_report_id')

    text = (
        f"**Report ID: {report_id}**\n\n"
        "Please type the reason or what info is needed from the reporter.\n\n"
        "Or tap 'Skip Reason' to send without a specific message."
    )
    keyboard = [
        [InlineKeyboardButton("Skip Reason (no message)", callback_data="admin_needs_info_no_reason")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_back_to_review")]
    ]

    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id

    return config.ADMIN_NEEDS_INFO_REASON


async def admin_needs_info_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin types the reason text."""
    try:
        await update.message.delete()
    except Exception:
        pass

    reason = update.message.text.strip()
    return await _set_needs_info(update, context, reason)


async def admin_needs_info_no_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin skips reason — set NEEDS_INFO without a message."""
    query = update.callback_query
    await query.answer()
    return await _set_needs_info(update, context, None)


async def _set_needs_info(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str = None) -> int:
    """Common logic: set report to NEEDS_INFO, notify reporter."""
    report_id = context.user_data.get('admin_current_report_id')
    report_data = context.user_data.get('admin_current_report_data')
    chat_id = update.effective_chat.id

    if not report_id or not report_data:
        await context.bot.send_message(chat_id=chat_id, text="Session expired. Please restart.")
        return ConversationHandler.END

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE reports
            SET report_status = 'NEEDS_INFO',
                needs_info_since = CURRENT_TIMESTAMP,
                admin_note = ?
            WHERE report_id = ?
        """, (reason, report_id))
        conn.commit()
        logger.info(f"Report {report_id} set to NEEDS_INFO (reason: {reason})")
    except sqlite3.Error as e:
        logger.error(f"DB error setting NEEDS_INFO: {e}")
    finally:
        conn.close()

    # Send notification to reporter
    reporter_user_id = report_data.get('submitter_user_id')
    if reporter_user_id:
        from bot_utils import send_report_notification
        await send_report_notification(
            bot=context.bot,
            reporter_user_id=reporter_user_id,
            report_id=report_id,
            notification_type='needs_info',
            reason=reason
        )

    # Confirm to admin
    prompt_id = context.user_data.get('prompt_message_id')
    await _safe_edit_message(
        context, chat_id, prompt_id,
        text=f"Report `{report_id}` set to NEEDS\\_INFO. Reporter has been notified.",
        reply_markup=None,
        parse_mode=ParseMode.MARKDOWN
    )

    context.user_data.pop('admin_current_report_id', None)
    context.user_data.pop('admin_current_report_data', None)

    return await admin_review_next_report(update, context)
