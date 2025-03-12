import signal
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from .config import BOT_TOKEN
from .utils import logger, load_groups, load_appeals_cache
from .handlers import start, register_merchant, register_trader_group, register_trader_username, list_groups, handle_message, handle_callback, remind_traders, debug_update

def shutdown(signum, frame, application):
    logger.info("Shutting down bot...")
    application.stop()
    logger.info("Bot stopped.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.bot_data["groups"] = load_groups()
    application.bot_data["appeals_cache"] = load_appeals_cache()
    logger.info(f"Loaded groups: {len(application.bot_data['groups']['merchant'])} merchants, {len(application.bot_data['groups']['trader'])} traders")
    logger.info(f"Loaded appeals cache: {len(application.bot_data['appeals_cache'])}")

    application.add_handler(MessageHandler(filters.ALL, debug_update, block=False), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register_merchant", register_merchant))
    application.add_handler(CommandHandler("register_trader_group", register_trader_group))
    application.add_handler(CommandHandler("register_trader_username", register_trader_username))
    application.add_handler(CommandHandler("listgroups", list_groups))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))

    application.job_queue.run_once(lambda ctx: asyncio.create_task(remind_traders(ctx)), 0)

    signal.signal(signal.SIGINT, lambda s, f: shutdown(s, f, application))
    signal.signal(signal.SIGTERM, lambda s, f: shutdown(s, f, application))

    logger.info("Starting polling...")
    application.run_polling(timeout=60)

if __name__ == "__main__":
    main()