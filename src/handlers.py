from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .utils import logger, escape_markdown_v2, load_groups, save_groups, load_appeals_cache, save_appeals_cache
from .api import get_appeal_status
from datetime import datetime, timedelta
import asyncio

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running! Use /register_merchant, /register_trader_group, or /register_trader_username <username> to set up.")

async def register_merchant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    groups = context.bot_data.get("groups", load_groups())
    if any(g["id"] == chat.id for g in groups["merchant"]):
        await update.message.reply_text("This group is already registered as a merchant group!")
        return
    groups["merchant"].append({"id": chat.id, "title": chat.title})
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info(f"Registered {chat.title} (ID: {chat.id}) as merchant")
    await update.message.reply_text(f"Registered {chat.title} as a merchant group.")

async def register_trader_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    groups = context.bot_data.get("groups", load_groups())
    if any(g["id"] == chat.id for g in groups["trader"]):
        await update.message.reply_text("This group is already registered as a trader group!")
        return
    groups["trader"].append({"id": chat.id, "title": chat.title})
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info(f"Registered {chat.title} (ID: {chat.id}) as trader group")
    await update.message.reply_text(f"Registered {chat.title} as a trader group. Now register a trader username with /register_trader_username <username>.")

async def register_trader_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    if not context.args:
        await update.message.reply_text("Usage: /register_trader_username <username>")
        return
    trader_username = context.args[0].lstrip('@')
    groups = context.bot_data.get("groups", load_groups())
    if chat.id not in [g["id"] for g in groups["trader"]]:
        logger.info(f"Failed to register trader username @{trader_username}: {chat.title} (ID: {chat.id}) is not a trader group")
        await update.message.reply_text("This group must be registered as a trader group first with /register_trader_group!")
        return
    groups["trader_accounts"][str(chat.id)] = trader_username
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info(f"Registered trader username @{trader_username} for group {chat.title} (ID: {chat.id})")
    await update.message.reply_text(f"Registered @{trader_username} as the trader for {chat.title}.")

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = context.bot_data.get("groups", load_groups())
    merchant_list = "\n".join(f"- {g['title']} (ID: {g['id']})" for g in groups["merchant"]) or "None"
    trader_list = "\n".join(f"- {g['title']} (ID: {g['id']}) @{groups['trader_accounts'].get(str(g['id']), 'No username')}" for g in groups["trader"]) or "None"
    response = f"Merchant Groups:\n{merchant_list}\n\nTrader Groups:\n{trader_list}"
    await update.message.reply_text(response)
    logger.info(f"Listed groups: Merchant={len(groups['merchant'])}, Trader={len(groups['trader'])}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        logger.info("No message in update, skipping")
        return

    chat = update.message.chat
    message_text = update.message.text.lower() if update.message.text else update.message.caption.lower() if update.message.caption else ""
    message_id = update.message.message_id

    logger.info(f"Received message in chat {chat.title} (ID: {chat.id}): '{message_text}'")
    logger.info(f"Message details - Photo: {bool(update.message.photo)}, Document: {bool(update.message.document)}, Video: {bool(update.message.video)}, Animation: {bool(update.message.animation)}")

    if message_text.startswith('/'):
        logger.info(f"Skipping message because it's a command: '{message_text}'")
        return

    groups = context.bot_data.get("groups", load_groups())
    is_merchant_group = any(g["id"] == chat.id for g in groups["merchant"])
    if not is_merchant_group:
        logger.info(f"Skipping message because {chat.title} (ID: {chat.id}) is not a merchant group")
        return

    if not message_text.strip():
        logger.info("Message text or caption is empty; prompting user")
        await update.message.reply_text("Please include text (e.g., trader name) with your appeal.")
        return

    message_words = message_text.strip().split()
    appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
    matched = False
    for trader_group in groups["trader"]:
        trader_title_lower = trader_group["title"].lower()
        trader_name = trader_title_lower.split(' | trader')[0]
        trader_name_words = trader_name.split()

        if any(word in trader_name_words for word in message_words):
            matched = True
            logger.info(f"Match found with trader group: {trader_group['title']}")
            keyboard = [[InlineKeyboardButton("Approve", callback_data=f"approve_{chat.id}_{message_id}"),
                        InlineKeyboardButton("Decline", callback_data=f"decline_{chat.id}_{message_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            appeal_id = f"APPEAL_{message_id}"
            forward_text = f"Payment appeal from {escape_markdown_v2(chat.title)} \\(Appeal ID: `{appeal_id}`\\): '{message_text}'"

            if update.message.photo:
                context.user_data[f"file_type_{message_id}"] = "photo"
                context.user_data[f"file_id_{message_id}"] = update.message.photo[-1].file_id
            elif update.message.document and update.message.document.mime_type in ["image/jpeg", "image/png", "application/pdf"]:
                context.user_data[f"file_type_{message_id}"] = "document"
                context.user_data[f"file_id_{message_id}"] = update.message.document.file_id
            elif update.message.video and update.message.video.mime_type == "video/mp4":
                context.user_data[f"file_type_{message_id}"] = "video"
                context.user_data[f"file_id_{message_id}"] = update.message.video.file_id
            elif update.message.animation and update.message.animation.mime_type == "video/mp4":
                context.user_data[f"file_type_{message_id}"] = "animation"
                context.user_data[f"file_id_{message_id}"] = update.message.animation.file_id
            else:
                context.user_data[f"file_type_{message_id}"] = None
                context.user_data[f"file_id_{message_id}"] = None

            try:
                if update.message.photo:
                    await context.bot.send_photo(
                        chat_id=trader_group["id"],
                        photo=context.user_data[f"file_id_{message_id}"],
                        caption=forward_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif update.message.document:
                    await context.bot.send_document(
                        chat_id=trader_group["id"],
                        document=context.user_data[f"file_id_{message_id}"],
                        caption=forward_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif update.message.video:
                    await context.bot.send_video(
                        chat_id=trader_group["id"],
                        video=context.user_data[f"file_id_{message_id}"],
                        caption=forward_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif update.message.animation:
                    await context.bot.send_animation(
                        chat_id=trader_group["id"],
                        animation=context.user_data[f"file_id_{message_id}"],
                        caption=forward_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=trader_group["id"],
                        text=forward_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                logger.info(f"Forwarded appeal to {trader_group['title']} (ID: {trader_group['id']})")

                trader_username = groups["trader_accounts"].get(str(trader_group["id"]), "")
                appeals_cache[f"{trader_group['id']}_{message_id}"] = {
                    "timestamp": datetime.now().isoformat(),
                    "trader_username": trader_username,
                    "chat_id": trader_group["id"],
                    "appeal_id": appeal_id
                }
                context.bot_data["appeals_cache"] = appeals_cache
                save_appeals_cache(appeals_cache)
                logger.info(f"Stored appeal {appeal_id} in cache for {trader_group['title']}")
                break
            except Exception as e:
                logger.error(f"Failed to forward to {trader_group['title']} (ID: {trader_group['id']}): {e}")
                await update.message.reply_text(f"Failed to send appeal: {e}")
                break
    if not matched:
        logger.info("No matching trader group found for this appeal")
        await update.message.reply_text("No matching trader group found.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    logger.info(f"Callback received: {data}")

    trader_username = query.from_user.username or query.from_user.first_name
    action, merchant_chat_id, message_id = data.split("_")
    merchant_chat_id = int(merchant_chat_id)
    trader_chat_id = query.message.chat_id
    response = "approved" if action == "approve" else "declined"
    appeal_id = f"APPEAL_{message_id}"

    file_type = context.user_data.get(f"file_type_{message_id}")
    file_id = context.user_data.get(f"file_id_{message_id}")

    # Check API for appeal status (example)
    appeal_status = get_appeal_status(appeal_id)
    if appeal_status and appeal_status.get("status") != "pending":
        logger.info(f"Appeal {appeal_id} already resolved via API: {appeal_status['status']}")
        await query.answer(f"Appeal already {appeal_status['status']}")
        return

    try:
        await context.bot.send_message(
            chat_id=merchant_chat_id,
            text=f"Trader response for `{appeal_id}`: {response}",
            reply_to_message_id=int(message_id),
            parse_mode="MarkdownV2"
        )
        logger.info(f"Sent response to merchant group {merchant_chat_id}")
    except Exception as e:
        logger.error(f"Failed to send to merchant group {merchant_chat_id}: {e}")

    try:
        await context.bot.delete_message(
            chat_id=trader_chat_id,
            message_id=query.message.message_id
        )
        logger.info(f"Deleted original message in trader group {trader_chat_id}")
    except Exception as e:
        logger.error(f"Failed to delete message in trader group {trader_chat_id}: {e}")

    escaped_username = escape_markdown_v2(trader_username)
    updated_text = f"{escaped_username} {response} `{appeal_id}`"
    retries = 3
    for attempt in range(retries):
        try:
            if file_type == "photo" and file_id:
                await context.bot.send_photo(
                    chat_id=trader_chat_id,
                    photo=file_id,
                    caption=updated_text,
                    parse_mode="MarkdownV2"
                )
            elif file_type == "document" and file_id:
                await context.bot.send_document(
                    chat_id=trader_chat_id,
                    document=file_id,
                    caption=updated_text,
                    parse_mode="MarkdownV2"
                )
            elif file_type == "video" and file_id:
                await context.bot.send_video(
                    chat_id=trader_chat_id,
                    video=file_id,
                    caption=updated_text,
                    parse_mode="MarkdownV2"
                )
            elif file_type == "animation" and file_id:
                await context.bot.send_animation(
                    chat_id=trader_chat_id,
                    animation=file_id,
                    caption=updated_text,
                    parse_mode="MarkdownV2"
                )
            else:
                await context.bot.send_message(
                    chat_id=trader_chat_id,
                    text=updated_text,
                    parse_mode="MarkdownV2"
                )
            logger.info(f"Reposted in trader group with text: '{updated_text}'")
            
            appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
            appeal_key = f"{trader_chat_id}_{message_id}"
            if appeal_key in appeals_cache:
                del appeals_cache[appeal_key]
                context.bot_data["appeals_cache"] = appeals_cache
                save_appeals_cache(appeals_cache)
                logger.info(f"Removed closed appeal {appeal_key} from cache")
            break
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{retries} failed to repost: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
            else:
                await context.bot.send_message(chat_id=trader_chat_id, text=f"Failed to repost after {retries} attempts: {e}")

async def remind_traders(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Starting trader reminder task")
    while True:
        try:
            appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
            now = datetime.now()
            reminder_intervals = [timedelta(minutes=1), timedelta(minutes=4), timedelta(minutes=8)]
            
            logger.info(f"Checking {len(appeals_cache)} cached appeals at {now}")
            for appeal_key, appeal_data in list(appeals_cache.items()):
                appeal_time = datetime.fromisoformat(appeal_data["timestamp"])
                trader_username = appeal_data["trader_username"]
                chat_id = appeal_data["chat_id"]
                appeal_id = appeal_data["appeal_id"]

                # Check API for latest status
                appeal_status = get_appeal_status(appeal_id)
                if appeal_status and appeal_status.get("status") != "pending":
                    logger.info(f"Appeal {appeal_id} resolved via API: {appeal_status['status']}")
                    del appeals_cache[appeal_key]
                    context.bot_data["appeals_cache"] = appeals_cache
                    save_appeals_cache(appeals_cache)
                    continue

                time_elapsed = now - appeal_time
                for interval in reminder_intervals:
                    seconds = interval.total_seconds()
                    if time_elapsed >= interval and f"reminded_{seconds}" not in appeal_data:
                        if not trader_username:
                            logger.warning(f"No trader username for appeal {appeal_id} in chat {chat_id}, skipping reminder")
                            continue
                        escaped_username = escape_markdown_v2(f"@{trader_username}")
                        minutes_str = str(seconds / 60).replace(".", "\\.")
                        reminder_text = f"{escaped_username}, reminder: Appeal `{appeal_id}` is still unclosed after {minutes_str} minutes\\."
                        logger.info(f"Attempting to send reminder: '{reminder_text}' to {chat_id}")
                        
                        retries = 3
                        for attempt in range(retries):
                            try:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=reminder_text,
                                    parse_mode="MarkdownV2"
                                )
                                logger.info(f"Sent reminder for {appeal_id} to @{trader_username} in {chat_id}")
                                appeal_data[f"reminded_{seconds}"] = True
                                appeals_cache[appeal_key] = appeal_data
                                context.bot_data["appeals_cache"] = appeals_cache
                                save_appeals_cache(appeals_cache)
                                break
                            except Exception as e:
                                logger.error(f"Attempt {attempt + 1}/{retries} failed to send reminder: {e}")
                                if attempt < retries - 1:
                                    await asyncio.sleep(5)
                                else:
                                    logger.error(f"All retries exhausted for reminder {appeal_id}")
        except Exception as e:
            logger.error(f"Reminder task error: {e}")
        await asyncio.sleep(60)

async def debug_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received update: {update.to_dict()}")