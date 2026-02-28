# main.py
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, 
    filters
)

# --- Import dari fail-fail kita ---
import config
from database import setup_database, migrate_social_media_columns, migrate_reports_columns
from image_generator import jinja_env
from handlers_general import start, cancel, show_statistics, auto_archive_needs_info

# Import semua fungsi handler dari fail masing-masing
from handlers_report import (
    report_start, get_title, get_description, get_reporter_status,
    get_report_type, get_phone_details, get_bank_details, get_social_details,
    ask_amount, get_amount, get_screenshots, screenshots_done,
    show_tos, submit_report, back_to_confirm,
    ask_add_phone, ask_add_bank, ask_add_social,
    get_add_phone, get_add_bank, get_add_social, add_cancel,
    back_to_title, back_to_description, back_to_reporter_status,
    back_to_report_type, back_to_phone_details, back_to_bank_details,
    back_to_social_details, back_to_amount, back_to_screenshots
)
from handlers_search import (
    search_start, search_profile, search_qr_image,  # ← TAMBAH SINI
    search_change_page, search_read_details,
    search_change_profile_reports_page, search_back_to_search_results,
    search_cancel_and_menu, list_banks_handler, list_phones_handler
)

from handlers_admin import (
    admin_start, admin_review_next_report, admin_verify_start,
    admin_dispute_report, admin_skip_report, admin_back_to_review,
    admin_link_profile, admin_ask_new_profile_name, admin_get_new_profile_name,
    admin_needs_info_start, admin_needs_info_reason, admin_needs_info_no_reason
)

from handlers_update import (
    start_report_update, update_report_description,
    update_report_screenshot, update_skip_screenshots,
    update_confirm_submit, update_cancel
)

from handlers_general import recheck_join

# === Setup Logging ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Setup dan jalankan bot."""
    
    # 1. Pastikan DB wujud
    setup_database()
    migrate_social_media_columns()
    migrate_reports_columns()

    # 2. Pastikan templat HTML wujud
    if not jinja_env:
        logger.critical("GAGAL: Jinja2 environment tidak dapat dimuatkan. Bot akan ditamatkan.")
        return
        
    # 3. Bina 'Application'
    application = Application.builder().token(config.BOT_TOKEN).build()

    # 4. Bina 'ConversationHandler' untuk Laporan
    report_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(report_start, pattern='^main_report$')
        ],
        states={
            config.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            config.DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_description),
                CallbackQueryHandler(back_to_title, pattern='^report_back_to_title$')
            ],
            config.REPORTER_STATUS: [
                CallbackQueryHandler(get_reporter_status, pattern='^report_status_'),
                CallbackQueryHandler(back_to_description, pattern='^report_back_to_desc$')
            ],
            config.REPORT_AGAINST_TYPE: [
                CallbackQueryHandler(get_report_type, pattern='^report_type_'),
                CallbackQueryHandler(back_to_reporter_status, pattern='^report_back_to_reporter_status$')
            ],
            config.GET_PHONE_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone_details),
                CallbackQueryHandler(back_to_report_type, pattern='^report_back_to_type$')
            ],
            config.GET_BANK_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_bank_details),
                CallbackQueryHandler(back_to_report_type, pattern='^report_back_to_type$')
            ],
            config.GET_SOCIAL_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_social_details),
                CallbackQueryHandler(back_to_report_type, pattern='^report_back_to_type$')
            ],
            config.GET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount),
                CallbackQueryHandler(back_to_phone_details, pattern='^report_back_to_phone_details$'),
                CallbackQueryHandler(back_to_bank_details, pattern='^report_back_to_bank_details$'),
                CallbackQueryHandler(back_to_social_details, pattern='^report_back_to_social_details$')
            ],
            config.GET_SCREENSHOTS: [
                MessageHandler(filters.PHOTO, get_screenshots),
                CallbackQueryHandler(screenshots_done, pattern='^report_done_screenshots$'),
                CallbackQueryHandler(back_to_amount, pattern='^report_back_to_amount$')
            ],
            config.CONFIRMATION: [
                CallbackQueryHandler(show_tos, pattern='^report_confirm_submit$'),
                CallbackQueryHandler(submit_report, pattern='^report_agree_tos$'),
                CallbackQueryHandler(back_to_confirm, pattern='^report_back_to_confirm$'),
                CallbackQueryHandler(back_to_screenshots, pattern='^report_back_to_screenshots$'),
                CallbackQueryHandler(ask_add_phone, pattern='^add_phone$'),
                CallbackQueryHandler(ask_add_bank, pattern='^add_bank$'),
                CallbackQueryHandler(ask_add_social, pattern='^add_social$'),
            ],
            config.ADD_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_add_phone),
                CallbackQueryHandler(add_cancel, pattern='^add_cancel$')
            ],
            config.ADD_BANK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_add_bank),
                CallbackQueryHandler(add_cancel, pattern='^add_cancel$')
            ],
            config.ADD_SOCIAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_add_social),
                CallbackQueryHandler(add_cancel, pattern='^add_cancel$')
            ],
            config.SEARCH_TERM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_profile),
                MessageHandler(filters.PHOTO, search_qr_image)
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(cancel, pattern='^cancel_report$')
        ],
        per_message=False
    )
    
    # 5. Bina 'ConversationHandler' untuk Carian
    search_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(search_start, pattern='^main_search$')
        ],
        states={
            config.SEARCH_TERM: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_profile)],
            config.SEARCH_RESULTS: [
                CallbackQueryHandler(search_change_page, pattern='^search_next$'),
                CallbackQueryHandler(search_change_page, pattern='^search_prev$'),
                CallbackQueryHandler(search_read_details, pattern='^search_read_report_'),
                CallbackQueryHandler(search_read_details, pattern='^search_read_profile_'),
                CallbackQueryHandler(search_cancel_and_menu, pattern='^main_menu_from_search$'),
                CallbackQueryHandler(lambda u, c: u.callback_query.answer("Tiada tindakan"), pattern='^search_nop$'),
                CallbackQueryHandler(list_banks_handler, pattern='^list_banks_'),
                CallbackQueryHandler(list_phones_handler, pattern='^list_phones_')
            ],
            config.VIEW_PROFILE_REPORTS: [
                CallbackQueryHandler(search_change_profile_reports_page, pattern='^prof_report_prev$'),
                CallbackQueryHandler(search_change_profile_reports_page, pattern='^prof_report_next$'),
                CallbackQueryHandler(search_read_details, pattern='^search_read_report_'),
                CallbackQueryHandler(search_back_to_search_results, pattern='^back_to_search_results$'),
                CallbackQueryHandler(lambda u, c: u.callback_query.answer("Tiada tindakan"), pattern='^search_nop$')
            ]
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern='^main_menu$'),
            CallbackQueryHandler(search_cancel_and_menu, pattern='^main_menu_from_search$'),
            CallbackQueryHandler(cancel, pattern='^cancel_report$') # Fallback umum
        ],
        per_message=False
    )
    
    # 6. Bina 'ConversationHandler' untuk Admin
    admin_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_start, pattern='^admin_menu$')
        ],
        states={
            config.ADMIN_MENU: [
                CallbackQueryHandler(admin_review_next_report, pattern='^admin_review_next$'),
                CallbackQueryHandler(start, pattern='^main_menu$')
            ],
            config.ADMIN_REVIEW_REPORT: [
                CallbackQueryHandler(admin_verify_start, pattern='^admin_verify$'),
                CallbackQueryHandler(admin_dispute_report, pattern='^admin_dispute$'),
                CallbackQueryHandler(admin_needs_info_start, pattern='^admin_needs_info$'),
                CallbackQueryHandler(admin_skip_report, pattern='^admin_skip$'),
                CallbackQueryHandler(admin_start, pattern='^admin_menu_back$')
            ],
            config.ADMIN_LINK_PROFILE: [
                CallbackQueryHandler(admin_link_profile, pattern='^admin_link_'),
                CallbackQueryHandler(admin_ask_new_profile_name, pattern='^admin_link_new$'),
                CallbackQueryHandler(admin_back_to_review, pattern='^admin_back_to_review$')
            ],
            config.ADMIN_NEW_PROFILE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_get_new_profile_name),
                CallbackQueryHandler(admin_back_to_review, pattern='^admin_back_to_review$')
            ],
            config.ADMIN_NEEDS_INFO_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_needs_info_reason),
                CallbackQueryHandler(admin_needs_info_no_reason, pattern='^admin_needs_info_no_reason$'),
                CallbackQueryHandler(admin_back_to_review, pattern='^admin_back_to_review$')
            ]
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern='^main_menu$'),
            CallbackQueryHandler(cancel, pattern='^cancel_report$') # Fallback umum
        ],
        per_message=False
    )
    

    # 6b. Deep link handler for report updates (/start update_<report_id>)
    async def _update_entry_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Check if /start has an update_<id> deep link arg; if so, route to update flow."""
        args = context.args
        if args and args[0].startswith('update_'):
            try:
                report_id = int(args[0].replace('update_', ''))
                return await start_report_update(update, context, report_id)
            except (ValueError, IndexError):
                pass
        # Not an update deep link — fall through to normal start
        return ConversationHandler.END

    update_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", _update_entry_check)
        ],
        states={
            config.UPDATE_REPORT_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, update_report_description),
                CallbackQueryHandler(update_cancel, pattern='^update_cancel$')
            ],
            config.UPDATE_REPORT_SCREENSHOTS: [
                MessageHandler(filters.PHOTO, update_report_screenshot),
                CallbackQueryHandler(update_skip_screenshots, pattern='^update_skip_screenshots$'),
                CallbackQueryHandler(update_cancel, pattern='^update_cancel$')
            ],
            config.UPDATE_REPORT_CONFIRM: [
                CallbackQueryHandler(update_confirm_submit, pattern='^update_confirm_submit$'),
                CallbackQueryHandler(update_cancel, pattern='^update_cancel$')
            ]
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(update_cancel, pattern='^update_cancel$')
        ],
        per_message=False
    )

    # 7. Tambah semua 'handler'
    # Conversation handlers FIRST — so their fallbacks can properly
    # end/reset conversations when user sends /start mid-conversation
    application.add_handler(update_conv_handler)  # Must be first — catches /start update_*
    application.add_handler(search_conv_handler)
    application.add_handler(report_conv_handler)
    application.add_handler(admin_conv_handler)

    # Standalone handlers AFTER — only catch updates when no conversation is active
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    
    application.add_handler(CallbackQueryHandler(recheck_join, pattern="^recheck_join$"))
    
    # 👉 GLOBAL QR HANDLER (WAJIB)
    application.add_handler(
        MessageHandler(filters.PHOTO, search_qr_image),
        group=5
    )

    application.add_handler(
        CallbackQueryHandler(show_statistics, pattern="^main_statistics$")
    )

    
    # 8. Setup JobQueue — auto-archive stale NEEDS_INFO reports every hour
    job_queue = application.job_queue
    job_queue.run_repeating(auto_archive_needs_info, interval=3600, first=60)

    # 9. Jalankan bot
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()