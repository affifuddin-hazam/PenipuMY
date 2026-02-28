# bot_utils.py
import logging
import json
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from typing import Union

logger = logging.getLogger(__name__)

async def _safe_edit_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
    parse_mode: str = ParseMode.MARKDOWN
) -> Union[Message, bool]:
    """
    Cuba edit mesej. Jika gagal (cth: mesej tak berubah), 
    'catch' error dan log 'warning' sahaja.
    """
    try:
        return await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Gagal edit mesej: Mesej tidak berubah.")
        elif "Message to edit not found" in str(e):
            logger.warning(f"Gagal edit mesej (ID: {message_id}): Mesej tidak dijumpai.")
        else:
            logger.error(f"Ralat BadRequest semasa edit mesej: {e}")
    except TelegramError as e:
        logger.error(f"Ralat Telegram semasa edit mesej: {e}")
    except Exception as e:
        logger.warning(f"Ralat 'Exception' tidak dijangka semasa edit mesej (ID: {message_id}): {e}")
    
    return False

async def _safe_delete_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int
):
    """Cuba padam mesej. 'Catch' error jika gagal."""
    if not message_id:
        logger.debug(f"Gagal padam mesej: message_id ialah 'None'. Diabaikan.")
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.warning(f"Gagal padam mesej (ID: {message_id}): {e}")

async def send_report_notification(
    bot,
    reporter_user_id: str,
    report_id: int,
    notification_type: str,
    reason: str = None
):
    """
    Send a Telegram notification to the reporter about their report status change.

    Args:
        bot: The Telegram Bot instance (context.bot)
        reporter_user_id: The Telegram user ID of the report submitter
        report_id: The report ID
        notification_type: One of 'verified', 'disputed', 'needs_info', 'auto_archived'
        reason: Optional reason text (for disputed/needs_info)
    """
    try:
        chat_id = int(reporter_user_id)
    except (ValueError, TypeError):
        logger.warning(f"Invalid reporter_user_id for notification: {reporter_user_id}")
        return False

    if notification_type == 'verified':
        text = (
            "Your report has been verified!\n\n"
            f"*Report ID:* `{report_id}`\n\n"
            "Your report has been reviewed and verified by our admin team. "
            "Thank you for helping the community stay safe from scams!"
        )
    elif notification_type == 'disputed':
        text = (
            "Your report status has been updated.\n\n"
            f"*Report ID:* `{report_id}`\n"
            f"*Status:* Disputed\n"
        )
        if reason:
            text += f"*Reason:* {reason}\n"
        text += (
            "\nIf you believe this is an error, you may submit a new report "
            "with additional evidence."
        )
    elif notification_type == 'needs_info':
        text = (
            "Admin needs more information about your report.\n\n"
            f"*Report ID:* `{report_id}`\n"
        )
        if reason:
            text += f"*Admin Note:* {reason}\n"
        text += (
            "\nPlease provide the requested information within 30 days, "
            "or the report will be automatically archived.\n\n"
            "Tap the button below to update your report."
        )
    elif notification_type == 'auto_archived':
        text = (
            "Your report has been automatically archived.\n\n"
            f"*Report ID:* `{report_id}`\n\n"
            "This report was marked as 'Needs Info' over 30 days ago "
            "but no additional information was provided. "
            "The report has been archived.\n\n"
            "You may submit a new report if you have the required information."
        )
    else:
        logger.warning(f"Unknown notification type: {notification_type}")
        return False

    try:
        keyboard = None
        if notification_type == 'needs_info':
            bot_info = await bot.get_me()
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Update Report",
                    url=f"https://t.me/{bot_info.username}?start=update_{report_id}"
                )
            ]])

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        logger.info(f"Notification sent to {reporter_user_id} for report {report_id} ({notification_type})")
        return True
    except TelegramError as e:
        logger.warning(f"Failed to send notification to {reporter_user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending notification to {reporter_user_id}: {e}")
        return False


def _format_confirmation_message(data: dict) -> str:
    """Helper untuk bina mesej rumusan (dipakai oleh Report & Admin)."""
    
    def get_val(key, default='N/A'):
        return data.get(key, default)

    text = "**STEP 8/8: Review & Submit**\n\n"
    text += "Please verify that all entered information is correct before submission.\n\n"
    
    text += f"**Title:** `{get_val('title')}`\n"
    text += f"**Description:** `{get_val('description')}`\n"
    
    amount = float(get_val('amount_scammed', 0))
    text += f"**Total Loss:** `RM{amount:.2f}`\n"
    
    report_type = get_val('report_against_type')
    
    text += "\n\n"
    if report_type == "PHONE":
        text += f"**Report Type:** Phone Number\n"
        text += f"**Phone Number:** `{get_val('against_phone_number')}`\n"
        text += f"**Name:** `{get_val('against_phone_name', 'N/A')}`\n"
    elif report_type == "BANK":
        text += f"**Report Type:** Bank Account\n"
        text += f"**Bank Account Number:** `{get_val('against_bank_number')}`\n"
        text += f"**Bank Name:** `{get_val('against_bank_name')}`\n"
        text += f"**Holder Name:** `{get_val('against_bank_holder_name')}`\n"
    elif report_type == "SOCIAL":
        text += f"**Report Type:** Social Media\n"
        text += f"**Username / URL:** `{get_val('against_social_url')}`\n"
        
    screenshots_count = len(data.get('screenshots', []))
    text += f"\n**Evidence:** `{screenshots_count} screenshots attached.`\n"
    
    evidence_list = data.get('additional_evidence', [])
    json_str = data.get('additional_info')
    
    if json_str and not evidence_list:
        try:
            evidence_list = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Gagal 'parse' JSON 'additional_info' dari DB: {json_str}")
            evidence_list = [f"Ralat Data: {json_str}"]
            
    if evidence_list:
        text += "\n**Additional Info**\n"
        for item in evidence_list:
            text += f"- `{item}`\n"
    
    return text