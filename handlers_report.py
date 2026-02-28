# handlers_report.py
import logging
import json
import sqlite3
from datetime import datetime
from config import ADMIN_USER_IDS
from typing import Union
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
from handlers_general import start # Perlu untuk 'submit'

logger = logging.getLogger(__name__)

# === Salin SEMUA fungsi dari Bahagian 6 (Laporan) ke sini ===
# (report_start, get_title, get_description, ...
# ... get_screenshots, _clear_screenshot_messages, screenshots_done, ...
# ... submit_report, ask_add_phone, get_add_phone, ...
# ... _return_to_confirmation, dll.)

# --- Contoh (saya takkan salin semua 1000+ baris, tapi ini strukturnya) ---

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    user_id = user.id
    logger.info(f"{user_id} entered report.")
    await query.answer()
    context.user_data.clear()
    context.user_data['report_data'] = {} 
    context.user_data['report_data']['additional_evidence'] = []
    
    text = (
        "STEP 1/8 : Report title.\n\n"
        "Tap on 'Cancel' if you would like to abort."
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=reply_markup
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id
    
    return config.TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Gagal padam mesej pengguna (get_title): {e}")

    title = update.message.text
    context.user_data['report_data']['title'] = title
    
    text = (
        "**STEP 2/8: Description**\n\n"
        "_*Type your description in one message. Avoid sending multiple message._"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Edit title", callback_data="report_back_to_title")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    
    prompt_id = context.user_data.get('prompt_message_id')
    await _safe_edit_message(
        context, update.effective_chat.id, prompt_id,
        text=text, 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Gagal padam mesej pengguna (get_description): {e}")

    description = update.message.text
    context.user_data['report_data']['description'] = description
    
    text = "**STEP 3/8: Reason for reporting**"
    keyboard = [
        [InlineKeyboardButton("I've been scammed", callback_data="report_status_SELF")],
        [InlineKeyboardButton("Someone else got scammed", callback_data="report_status_OTHER")],
        [InlineKeyboardButton("Spreading awareness", callback_data="report_status_AWARENESS")],
        [InlineKeyboardButton("⬅️ Edit description", callback_data="report_back_to_desc")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")],
    ]
    
    prompt_id = context.user_data.get('prompt_message_id')
    await _safe_edit_message(
        context, update.effective_chat.id, prompt_id,
        text=text, 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.REPORTER_STATUS

async def get_reporter_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    status_choice = query.data.split('_')[-1]
    status_map = {
        "SELF": "I'VE BEEN SCAMMED",
        "OTHER": "SOMEONE ELSE GOT SCAMMED",
        "AWARENESS": "RAISING AWARENESS"
    }
    context.user_data['report_data']['reporter_status'] = status_map.get(status_choice, "UNKNOWN")

    text = f"**STEP 4/8: What type of information would you like to report?**"
    keyboard = [
        [InlineKeyboardButton("Phone Number", callback_data="report_type_PHONE")],
        [InlineKeyboardButton("Bank Account", callback_data="report_type_BANK")],
        [InlineKeyboardButton("Social Media", callback_data="report_type_SOCIAL")],
        [InlineKeyboardButton("⬅️ Edit Status", callback_data="report_back_to_reporter_status")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")],
    ]
    
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.REPORT_AGAINST_TYPE

async def get_report_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    report_type = choice.split('_')[-1]
    
    context.user_data['report_data']['report_against_type'] = report_type
    logger.info(f"Data laporan dikemaskini (jenis laporan): {context.user_data['report_data']}")

    text = ""
    next_state = None
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Reselect Type", callback_data="report_back_to_type")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if report_type == "PHONE":
        text = (
            "**STEP 5/8: Please enter the phone number.**\n\n"
            "Format : `NUMBER, NAME` (Name is *optional*)\n"
            "Example: `0123456789, JNT Scammer`\n"
            "Example: `0123456789`"
        )
        next_state = config.GET_PHONE_DETAILS
        
    elif report_type == "BANK":
        text = (
            "**STEP 5/8: Please enter the bank details**\n\n"
            "Format : `ACCOUNT NUMBER, BANK NAME, ACCOUNT HOLDER NAME`\n"
            "Example: `112233445566, MAYBANK, Siti Keldai`\n"
            "Example: `112233445666, UNKNOWN, Man Kerbau`"
        )
        next_state = config.GET_BANK_DETAILS
        
    elif report_type == "SOCIAL":
        text = (
            "**STEP 5/8: Please enter the social media URL.**\n\n"
            "Example: `facebook.com/scammerpage`\n"
            "Example: `instagram.com/scam.invest`"
        )
        next_state = config.GET_SOCIAL_DETAILS
        
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=reply_markup
    )
    return next_state

async def get_phone_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception: pass

    details = update.message.text
    parts = [part.strip() for part in details.split(',', 1)]
    
    context.user_data['report_data']['against_phone_number'] = parts[0]
    context.user_data['report_data']['against_phone_name'] = parts[1] if len(parts) > 1 else None
            
    logger.info(f"Data laporan dikemaskini (phone): {context.user_data['report_data']}")
    
    return await ask_amount(update, context, "report_back_to_phone_details")

async def get_bank_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception: pass
        
    prompt_id = context.user_data.get('prompt_message_id')
    chat_id = update.effective_chat.id
    
    details = update.message.text
    parts = [part.strip() for part in details.split(',', 2)]
    
    if len(parts) < 3:
        text = (
            "❌ **Invalid format. Please try again.**\n\n"
            "Please make sure you send 3 parts separated by commas (,)\n\n"
            "Example: `112233445566, MAYBANK, Siti Keldai`"
            "Example: `112233445666, UNKNOWN, Man Kerbau`"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Reselect Type", callback_data="report_back_to_type")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
        ]
        
        await _safe_edit_message(
            context, chat_id, prompt_id,
            text=text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return config.GET_BANK_DETAILS

    context.user_data['report_data']['against_bank_number'] = parts[0]
    context.user_data['report_data']['against_bank_name'] = parts[1]
    context.user_data['report_data']['against_bank_holder_name'] = parts[2]
    
    logger.info(f"Data laporan dikemaskini (bank): {context.user_data['report_data']}")
    
    return await ask_amount(update, context, "report_back_to_bank_details")

async def get_social_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception: pass

    url = update.message.text
    context.user_data['report_data']['against_social_url'] = url
    logger.info(f"Data laporan dikemaskini (social): {context.user_data['report_data']}")

    return await ask_amount(update, context, "report_back_to_social_details")

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, back_callback_data: str) -> int:
    text = (
        "**STEP 6/8: What is the total amount of loss (RM)?**\n\n"
        "Please enter the amount only, without 'RM'.\n"
        "If there is no financial loss (e.g. 'Spreading Awareness'), enter `0`."
    )
    keyboard = [
        [InlineKeyboardButton(f"⬅️ Edit Info", callback_data=back_callback_data)],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    
    prompt_id = context.user_data.get('prompt_message_id')
    chat_id = None
    message_id = None

    if update.message:
        chat_id = update.effective_chat.id
        message_id = prompt_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
        message_id = update.callback_query.message.message_id
    
    msg = None
    if chat_id and message_id:
        msg = await _safe_edit_message(
            context, chat_id, message_id,
            text=text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id

    return config.GET_AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.delete()
    except Exception: pass
        
    prompt_id = context.user_data.get('prompt_message_id')
    chat_id = update.effective_chat.id
    amount_text = update.message.text
    
    try:
        amount = float(amount_text.replace("RM", "").strip())
        context.user_data['report_data']['amount_scammed'] = amount
        logger.info(f"Data laporan dikemaskini (amount): {context.user_data['report_data']}")

        text = (
            f"**STEP 7/8: Please send *screenshots* as evidence.**\n\n"
            f"At least 1 screenshot is required.\n"
            f"You can send up to {config.MAX_SCREENSHOTS} photos (one by one).\n"
            f"*(0/{config.MAX_SCREENSHOTS} photo(s) uploaded)*"
        )
        keyboard = [
            [InlineKeyboardButton("Done Uploading", callback_data="report_done_screenshots")],
            [InlineKeyboardButton("⬅️ Edit Amount", callback_data="report_back_to_amount")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
        ]
        
        msg = await _safe_edit_message(
            context, chat_id, prompt_id,
            text=text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        if msg:
            context.user_data['screenshot_prompt_id'] = msg.message_id
        
        context.user_data['report_data']['screenshots'] = []
        context.user_data.pop('last_screenshot_reply_id', None)
        
        return config.GET_SCREENSHOTS
        
    except ValueError:
        text = (
            "❌ **Invalid format. Please enter numbers only.**\n\n"
            "Example: `1500` or `0`.\n\n"
            "**STEP 6/8: What is the total amount of loss (RM)?**"
        )
        report_type = context.user_data['report_data'].get('report_against_type', 'PHONE')
        back_callback = "report_back_to_phone_details"
        if report_type == "BANK":
            back_callback = "report_back_to_bank_details"
        elif report_type == "SOCIAL":
            back_callback = "report_back_to_social_details"
            
        keyboard = [
            [InlineKeyboardButton(f"⬅️ Edit Info", callback_data=back_callback)],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
        ]

        await _safe_edit_message(
            context, chat_id, prompt_id,
            text=text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return config.GET_AMOUNT

async def back_to_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = (
        "**You are back at STEP 1/8: What is the title of this report?**\n\n"
        "Example: Scammer Susah.My, Scammer TLDM"
    )
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id
    return config.TITLE

async def back_to_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('report_data', {})
    text = (
        "**You are back at STEP 2/8: Please write your description of the report.**\n\n"
        f"Current Description: `{data.get('description', 'None')}`"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Edit Title", callback_data="report_back_to_title")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.DESCRIPTION

async def back_to_reporter_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = "**STEP 3/8: Reason for reporting?**"
    keyboard = [
        [InlineKeyboardButton("I've been scammed", callback_data="report_status_SELF")],
        [InlineKeyboardButton("Someone else got scammed", callback_data="report_status_OTHER")],
        [InlineKeyboardButton("Spreading awareness", callback_data="report_status_AWARENESS")],
        [InlineKeyboardButton("⬅️ Edit Description", callback_data="report_back_to_desc")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")],
    ]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.REPORTER_STATUS

async def back_to_report_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = f"**You are back at STEP 4/8: What type of information would you like to report?**"
    keyboard = [
        [InlineKeyboardButton("Phone Number", callback_data="report_type_PHONE")],
        [InlineKeyboardButton("Bank Account", callback_data="report_type_BANK")],
        [InlineKeyboardButton("Social Media Username / URL", callback_data="report_type_SOCIAL")],
        [InlineKeyboardButton("⬅️ Edit Status", callback_data="report_back_to_reporter_status")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")],
    ]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.REPORT_AGAINST_TYPE

async def back_to_phone_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('report_data', {})
    text = (
        "**You are back at STEP 5/8: Please enter the phone number.**\n\n"
        "Format: `NUMBER, NAME` (Name is *optional*)\n"
        f"Current Data: `{data.get('against_phone_number', '')}, {data.get('against_phone_name', '')}`"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Reselect Type", callback_data="report_back_to_type")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.GET_PHONE_DETAILS

async def back_to_bank_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('report_data', {})
    text = (
        "**You are back at STEP 5/8: Please enter bank details.**\n\n"
        "Format: `ACCOUNT NUMBER, BANK NAME, HOLDER NAME`\n"
        f"Current data: `{data.get('against_bank_number', '')}, {data.get('against_bank_name', '')}, {data.get('against_bank_holder_name', '')}`"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Reselect Type", callback_data="report_back_to_type")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.GET_BANK_DETAILS

async def back_to_social_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('report_data', {})
    text = (
        "**You are back at STEP 5/8: Please enter social media URL.**\n\n"
        f"Current data: `{data.get('against_social_url', '')}`"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Reselect Type", callback_data="report_back_to_type")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.GET_SOCIAL_DETAILS

async def back_to_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    #await _clear_screenshot_messages(update, context)
    last_reply_id = context.user_data.pop('last_screenshot_reply_id', None)
    if last_reply_id:
        await _safe_delete_message(context, update.effective_chat.id, last_reply_id)
    
    data = context.user_data.get('report_data', {})
    report_type = data.get('report_against_type', 'PHONE')
    back_callback = "report_back_to_phone_details"
    if report_type == "BANK":
        back_callback = "report_back_to_bank_details"
    elif report_type == "SOCIAL":
        back_callback = "report_back_to_social_details"
        
    return await ask_amount(update, context, back_callback)

async def _clear_screenshot_messages(update: Union[Update, CallbackQuery], context: ContextTypes.DEFAULT_TYPE):
    chat_id = None
    if update.effective_chat:
        chat_id = update.effective_chat.id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    
    if not chat_id:
        logger.warning("_clear_screenshot_messages: Tidak dapat 'detect' chat_id.")
        return

    last_reply_id = context.user_data.pop('last_screenshot_reply_id', None)
    if last_reply_id:
        await _safe_delete_message(context, chat_id, last_reply_id)
    
    prompt_id = context.user_data.pop('screenshot_prompt_id', None)
    if prompt_id:
        await _safe_delete_message(context, chat_id, prompt_id)

async def get_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'screenshots' not in context.user_data['report_data']:
        context.user_data['report_data']['screenshots'] = []
        
    screenshots = context.user_data['report_data']['screenshots']
    
    if len(screenshots) >= config.MAX_SCREENSHOTS:
        await _safe_delete_message(context, update.message.chat_id, update.message.message_id)
        msg = await update.message.reply_text(
            f"You had reached maximum {config.MAX_SCREENSHOTS} photos. Please tap 'Done Uploading'."
        )
        return config.GET_SCREENSHOTS

    file_id = update.message.photo[-1].file_id
    screenshots.append(file_id)
    
    logger.info(f"Gambar ditambah: {file_id}. Total: {len(screenshots)}")

    last_reply_id = context.user_data.pop('last_screenshot_reply_id', None)
    if last_reply_id:
        await _safe_delete_message(context, update.effective_chat.id, last_reply_id)
    
    prompt_id = context.user_data.pop('screenshot_prompt_id', None)
    if prompt_id:
        await _safe_delete_message(context, update.effective_chat.id, prompt_id)

    text = (
        f"{len(screenshots)}/{config.MAX_SCREENSHOTS} photo(s) received.\n\n"
        "You may send more, or tap 'Done Uploading' when finished."
    )
    keyboard = [
        [InlineKeyboardButton("Done Uploading", callback_data="report_done_screenshots")],
        [InlineKeyboardButton("⬅️ Edit Amount", callback_data="report_back_to_amount")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['last_screenshot_reply_id'] = msg.message_id
    
    return config.GET_SCREENSHOTS

async def screenshots_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    data = context.user_data['report_data']
    screenshots = data.get('screenshots', [])
    if not screenshots:
        await query.answer("Please upload at least one screenshot as evidence.", show_alert=True)
        return config.GET_SCREENSHOTS

    await query.answer()
    await _clear_screenshot_messages(update, context)
    
    text = _format_confirmation_message(data) # Guna dari bot_utils
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Submit", callback_data="report_confirm_submit")],
        [
            InlineKeyboardButton("+ Phone Number", callback_data="add_phone"),
            InlineKeyboardButton("+ Bank Account", callback_data="add_bank"),
            InlineKeyboardButton("+ Social Media", callback_data="add_social"),
        ],
        [InlineKeyboardButton("⬅️ Add More Screenshots", callback_data="report_back_to_screenshots")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    screenshots = data.get('screenshots', [])
    if screenshots:
        try:
            media_group = [InputMediaPhoto(media=file_id) for file_id in screenshots]
            album_messages = await query.message.reply_media_group(media=media_group)
            context.user_data['preview_album_ids'] = [m.message_id for m in album_messages]
        except Exception as e:
            logger.error(f"Gagal hantar album: {e}")
            await query.message.reply_text("Ralat: Gagal memaparkan gambar bukti.")

    msg = await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    context.user_data['prompt_message_id'] = msg.message_id
    
    return config.CONFIRMATION

async def back_to_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    album_ids = context.user_data.pop('preview_album_ids', [])
    for msg_id in album_ids:
        await _safe_delete_message(context, query.message.chat_id, msg_id)
    
    screenshots_count = len(context.user_data['report_data'].get('screenshots', []))
    
    text = (
        f"**You are back at STEP 7/8: Please send *screenshots* as evidence.**\n\n"
        f"At least 1 screenshot is required.\n"
        f"You can send up to {config.MAX_SCREENSHOTS} photos (one by one).\n\n"
        f"*({screenshots_count}/{config.MAX_SCREENSHOTS} photo(s) uploaded)*\n"
    )
    keyboard = [
        [InlineKeyboardButton("Done Uploading", callback_data="report_done_screenshots")],
        [InlineKeyboardButton("⬅️ Edit Amount", callback_data="report_back_to_amount")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")]
    ]
    
    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    if msg:
        context.user_data['screenshot_prompt_id'] = msg.message_id
    
    context.user_data.pop('last_screenshot_reply_id', None)
    context.user_data.pop('prompt_message_id', None)

    return config.GET_SCREENSHOTS

async def show_tos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show Terms of Submission before final submit."""
    query = update.callback_query
    await query.answer()

    tos_text = (
        "⚠️ *Terms of Submission*\n\n"
        "By submitting this report, you acknowledge and agree to the following:\n\n"
        "• All information provided is *true and accurate* to the best of your knowledge.\n"
        "• Submitting a *false or malicious report* is a serious offence and may result in your account being *permanently banned* and potential *legal consequences*.\n"
        "• Your report will be made *publicly visible* to help protect others from scams.\n"
        "• PenipuMY reserves the right to *verify, edit, or remove* any report at its discretion.\n\n"
        "Do you agree to these terms?"
    )

    keyboard = [
        [InlineKeyboardButton("✅ I Agree & Submit", callback_data="report_agree_tos")],
        [InlineKeyboardButton("⬅️ Go Back", callback_data="report_back_to_confirm")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=tos_text, reply_markup=reply_markup
    )
    if msg:
        context.user_data['prompt_message_id'] = msg.message_id

    return config.CONFIRMATION


async def submit_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Processing report...")

    user_id = str(update.effective_user.id)
    data = context.user_data['report_data']
    
    linked_profile_id = None
    report_type = data.get('report_against_type')
    search_key = None
    search_value = None
    search_table = None

    if report_type == "PHONE":
        search_key = "phone_number"
        search_value = data.get('against_phone_number')
        search_table = "profile_phone_numbers"
    elif report_type == "BANK":
        search_key = "account_number"
        search_value = data.get('against_bank_number')
        search_table = "profile_bank_accounts"
    elif report_type == "SOCIAL":
        search_key = "url"
        search_value = data.get('against_social_url')
        search_table = "profile_social_media"

    if search_value and search_table:
        conn_check = get_db_connection()
        try:
            cursor_check = conn_check.cursor()
            query_sql = f"""
            SELECT p.profile_id
            FROM profiles p
            JOIN {search_table} t ON p.profile_id = t.profile_id
            WHERE t.{search_key} = ?
            """
            cursor_check.execute(query_sql, (search_value,))
            existing_profiles = cursor_check.fetchall()
            
            if len(existing_profiles) == 1:
                linked_profile_id = existing_profiles[0]['profile_id']
                logger.info(f"Laporan baru (dari {user_id}) di-auto-link ke profil: {linked_profile_id}")
    
        except sqlite3.Error as e:
            logger.error(f"Ralat DB semasa auto-link check: {e}")
        finally:
            conn_check.close()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        additional_evidence_list = data.get('additional_evidence', [])
        additional_info_json = json.dumps(additional_evidence_list)
        
        report_sql = """
        INSERT INTO reports (
            submitter_user_id, title, description, reporter_status, amount_scammed, 
            report_against_type, against_phone_number, against_phone_name, 
            against_bank_number, against_bank_name, against_bank_holder_name, 
            against_social_url, additional_info, linked_profile_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        report_values = (
            user_id,
            data.get('title'),
            data.get('description'),
            data.get('reporter_status'),
            data.get('amount_scammed', 0),
            data.get('report_against_type'),
            data.get('against_phone_number'),
            data.get('against_phone_name'),
            data.get('against_bank_number'),
            data.get('against_bank_name'),
            data.get('against_bank_holder_name'),
            data.get('against_social_url'),
            additional_info_json,
            linked_profile_id
        )
        
        cursor.execute(report_sql, report_values)
        new_report_id = cursor.lastrowid
        
        logger.info(f"Laporan baru (ID: {new_report_id}) berjaya disimpan.")
        
        screenshots = data.get('screenshots', [])
        if screenshots:
            screenshot_sql = "INSERT INTO screenshots (report_id, file_path) VALUES (?, ?)"
            screenshot_values = [(new_report_id, file_id) for file_id in screenshots]
            cursor.executemany(screenshot_sql, screenshot_values)
            logger.info(f"{len(screenshots)} screenshots disimpan untuk report ID: {new_report_id}")
            
        conn.commit()
        
        text = (
            "✅ Your report has been successfully submitted and will be reviewed by admin.\n\n"
            f"**Report ID:** `{new_report_id}`\n"
            "Thank you for helping the community."
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🔍 Search", callback_data="main_search"),
                InlineKeyboardButton("➕ Report", callback_data="main_report"),
            ]
        ]

        if user_id in ADMIN_USER_IDS:
            logger.info(f"Admin (ID: {user_id}) telah memulakan bot.")
            keyboard.append(
                [InlineKeyboardButton("🛡️ Admin Panel", callback_data="admin_menu")]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )

    except sqlite3.Error as e:
        logger.error(f"Ralat database semasa simpan laporan: {e}")
        await _safe_edit_message(
            context, query.message.chat_id, query.message.message_id,
            text="Sorry, an error occurred while saving your report.",
            reply_markup=None
        )
    finally:
        if conn:
            conn.close()
            
    context.user_data.clear()
        
    #await start(update, context)
    return ConversationHandler.END

async def ask_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = (
        "**Additional Information**\n\n"
        "Please enter the **Phone Number**.\n"
        "Format : `NUMBER, NAME` (Name is *optional*)\n"
        "Example: `011234567, Ahmad Runner`"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel & Return to Summary", callback_data="add_cancel")]]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.ADD_PHONE

async def ask_add_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = (
        "**Additional Information**\n\n"
        "Please enter the **Bank Account** information.\n"
        "Format : `ACCOUNT NUMBER, BANK NAME, HOLDER NAME`\n"
        "Example: `987654321, RHB, Mohd Kassim`"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel & Return to Summary", callback_data="add_cancel")]]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.ADD_BANK

async def ask_add_social(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = (
        "**Additional Information**\n\n"
        "Please enter the **Social Media** URL.\n"
        "Example: `tiktok.com/@scammer`"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel & Return to Summary", callback_data="add_cancel")]]
    await _safe_edit_message(
        context, query.message.chat_id, query.message.message_id,
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return config.ADD_SOCIAL

async def get_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.delete()
    data = update.message.text
    context.user_data['report_data']['additional_evidence'].append(f"Telefon: {data}")
    logger.info(f"Maklumat tambahan ditambah: {data}")
    return await _return_to_confirmation(update, context)

async def get_add_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.delete()
    data = update.message.text
    context.user_data['report_data']['additional_evidence'].append(f"Bank: {data}")
    logger.info(f"Maklumat tambahan ditambah: {data}")
    return await _return_to_confirmation(update, context)

async def get_add_social(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.delete()
    data = update.message.text
    context.user_data['report_data']['additional_evidence'].append(f"Sosial: {data}")
    logger.info(f"Maklumat tambahan ditambah: {data}")
    return await _return_to_confirmation(update, context)

async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await _return_to_confirmation(update, context)

async def _return_to_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data['report_data']
    text = _format_confirmation_message(data) # Guna dari bot_utils
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Submit", callback_data="report_confirm_submit")],
        [
            InlineKeyboardButton("+ Phone Number", callback_data="add_phone"),
            InlineKeyboardButton("+ Bank Account", callback_data="add_bank"),
            InlineKeyboardButton("+ Social Media", callback_data="add_social"),
        ],
        [InlineKeyboardButton("⬅️ Edit Screenshots", callback_data="report_back_to_screenshots")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_report")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    chat_id = update.effective_chat.id
    prompt_id = context.user_data.get('prompt_message_id')

    msg = await _safe_edit_message(
        context, chat_id, prompt_id,
        text=text, reply_markup=reply_markup
    )
    if not msg:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )

    if msg:
        context.user_data['prompt_message_id'] = msg.message_id
        
    return config.CONFIRMATION

async def back_to_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back from TOS screen to confirmation screen."""
    query = update.callback_query
    await query.answer()
    return await _return_to_confirmation(update, context)

# (Salin semua fungsi lain dari Bahagian 6 ke sini)