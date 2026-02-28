# handlers_update.py
"""
Handler for reporters to update reports that are in NEEDS_INFO status.
Triggered via deep link: /start update_<report_id>
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import config
from database import get_db_connection
from bot_utils import _safe_edit_message, _safe_delete_message

logger = logging.getLogger(__name__)


async def start_report_update(update: Update, context: ContextTypes.DEFAULT_TYPE, report_id: int) -> int:
    """Entry point for report update flow, called from start() with deep link."""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    # Validate: report exists, belongs to this user, is in NEEDS_INFO or auto_rejected
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reports WHERE report_id = ? AND submitter_user_id = ?",
            (report_id, user_id)
        )
        report = cursor.fetchone()

        if not report:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Report not found or you do not have permission to update this report."
            )
            return ConversationHandler.END

        report_dict = {key: report[key] for key in report.keys()}

        # Allow NEEDS_INFO or auto-rejected reports
        is_auto_rejected = (report_dict.get('report_status') == 'REJECTED'
                            and report_dict.get('auto_rejected') == 1)
        if report_dict.get('report_status') != 'NEEDS_INFO' and not is_auto_rejected:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"This report (ID: {report_id}) is not currently awaiting additional information.\n"
                    f"Current status: {report_dict.get('report_status')}"
                )
            )
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error fetching report for update: {e}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred. Please try again.")
        return ConversationHandler.END
    finally:
        conn.close()

    # Store report data in context
    context.user_data.clear()
    context.user_data['update_report_id'] = report_id
    context.user_data['update_report_data'] = report_dict

    admin_note = report_dict.get('admin_note', '')

    text = f"*Update Report (ID: {report_id})*\n\n"
    if admin_note:
        text += f"*Admin's request:* {admin_note}\n\n"
    text += (
        "Please type your updated description or additional information.\n"
        "Send it in a single message."
    )

    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data="update_cancel")]
    ]

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['prompt_message_id'] = msg.message_id

    return config.UPDATE_REPORT_DESC


async def update_report_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reporter sends updated description."""
    try:
        await update.message.delete()
    except Exception:
        pass

    new_description = update.message.text.strip()
    context.user_data['update_new_description'] = new_description

    prompt_id = context.user_data.get('prompt_message_id')
    chat_id = update.effective_chat.id

    text = (
        "*Update Report*\n\n"
        "Would you like to add new screenshots?\n\n"
        "Send photos now, or tap 'Skip' to submit without new screenshots."
    )
    keyboard = [
        [InlineKeyboardButton("Skip (No new screenshots)", callback_data="update_skip_screenshots")],
        [InlineKeyboardButton("Cancel", callback_data="update_cancel")]
    ]

    context.user_data['update_screenshots'] = []

    msg = await _safe_edit_message(
        context, chat_id, prompt_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id

    return config.UPDATE_REPORT_SCREENSHOTS


async def update_report_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reporter sends a screenshot for the update."""
    screenshots = context.user_data.get('update_screenshots', [])

    if len(screenshots) >= config.MAX_SCREENSHOTS:
        await update.message.reply_text(
            f"Maximum {config.MAX_SCREENSHOTS} photos reached. Tap 'Done' to continue."
        )
        return config.UPDATE_REPORT_SCREENSHOTS

    file_id = update.message.photo[-1].file_id
    screenshots.append(file_id)
    context.user_data['update_screenshots'] = screenshots

    # Delete previous reply if exists
    last_reply_id = context.user_data.pop('update_last_reply_id', None)
    if last_reply_id:
        await _safe_delete_message(context, update.effective_chat.id, last_reply_id)

    text = f"{len(screenshots)}/{config.MAX_SCREENSHOTS} new photo(s) received."
    keyboard = [
        [InlineKeyboardButton("Done", callback_data="update_skip_screenshots")],
        [InlineKeyboardButton("Cancel", callback_data="update_cancel")]
    ]

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['update_last_reply_id'] = msg.message_id

    return config.UPDATE_REPORT_SCREENSHOTS


async def update_skip_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reporter skips screenshots or is done uploading."""
    query = update.callback_query
    await query.answer()

    report_id = context.user_data.get('update_report_id')
    new_desc = context.user_data.get('update_new_description', '')
    new_screenshots = context.user_data.get('update_screenshots', [])

    # Truncate description preview for confirmation
    desc_preview = new_desc[:200] + '...' if len(new_desc) > 200 else new_desc

    text = (
        f"*Confirm Update for Report ID: {report_id}*\n\n"
        f"*New Description:*\n{desc_preview}\n\n"
        f"*New Screenshots:* {len(new_screenshots)} photo(s)\n\n"
        "Tap 'Submit Update' to confirm."
    )
    keyboard = [
        [InlineKeyboardButton("Submit Update", callback_data="update_confirm_submit")],
        [InlineKeyboardButton("Cancel", callback_data="update_cancel")]
    ]

    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

    return config.UPDATE_REPORT_CONFIRM


async def update_confirm_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reporter confirms the update — save to DB, revert status to UNVERIFIED."""
    query = update.callback_query
    await query.answer("Processing...")

    report_id = context.user_data.get('update_report_id')
    new_desc = context.user_data.get('update_new_description', '')
    new_screenshots = context.user_data.get('update_screenshots', [])

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Append new description to existing (preserve history)
        cursor.execute("SELECT description FROM reports WHERE report_id = ?", (report_id,))
        row = cursor.fetchone()
        old_desc = row['description'] if row else ''

        updated_desc = f"{old_desc}\n\n--- UPDATE ---\n{new_desc}"

        cursor.execute("""
            UPDATE reports
            SET description = ?,
                report_status = 'UNVERIFIED',
                restored_at = CURRENT_TIMESTAMP,
                needs_info_since = NULL,
                admin_note = NULL,
                auto_rejected = 0,
                rejection_reason = NULL
            WHERE report_id = ?
        """, (updated_desc, report_id))

        # Save new screenshots
        if new_screenshots:
            screenshot_sql = "INSERT INTO screenshots (report_id, file_path) VALUES (?, ?)"
            screenshot_values = [(report_id, file_id) for file_id in new_screenshots]
            cursor.executemany(screenshot_sql, screenshot_values)

        conn.commit()
        logger.info(f"Report {report_id} updated by reporter, status reverted to UNVERIFIED")

        # Notify admin(s) that the report has been updated
        for admin_id in config.ADMIN_USER_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"*Report Updated*\n\n"
                        f"Report ID `{report_id}` has been updated by the reporter "
                        f"with new information. Status reverted to UNVERIFIED.\n\n"
                        f"Please review in Admin Panel."
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")

        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text=(
                f"Your update for Report ID `{report_id}` has been submitted.\n\n"
                "The report will be re-reviewed by our admin team. Thank you!"
            ),
            reply_markup=None,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Failed to update report {report_id}: {e}")
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text="An error occurred while updating the report. Please try again.",
            reply_markup=None
        )
    finally:
        conn.close()

    context.user_data.clear()
    return ConversationHandler.END


async def update_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reporter cancels the update."""
    query = update.callback_query
    await query.answer()

    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text="Update cancelled.",
        reply_markup=None
    )

    context.user_data.clear()
    return ConversationHandler.END
