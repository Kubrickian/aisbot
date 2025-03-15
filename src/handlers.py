from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from .utils import logger, escape_markdown_v2, load_groups, save_groups, load_appeals_cache, save_appeals_cache, set_chat_context
from .api import api_manager
from datetime import datetime, timedelta
import asyncio
import re

# Define states for the conversation
WAITING_FOR_MESSAGE, WAITING_FOR_APPEAL_ID = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.chat_info = set_chat_context(update.message.chat)
    await update.message.reply_text("Bot is running! Use /register_merchant, /register_trader_group, or /register_trader_username <username> to set up.")

async def register_merchant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    groups = context.bot_data.get("groups", load_groups())
    if any(g["id"] == chat.id for g in groups["merchant"]):
        await update.message.reply_text("This group is already registered as a merchant group!")
        return
    groups["merchant"].append({"id": chat.id, "title": chat.title, "appeal_id_start_pos": 0, "appeal_id_length": 0})  # Default
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info("Registered %s as merchant", chat.title)
    await update.message.reply_text(f"Registered {chat.title} as a merchant group.")

async def register_trader_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    groups = context.bot_data.get("groups", load_groups())
    if any(g["id"] == chat.id for g in groups["trader"]):
        await update.message.reply_text("This group is already registered as a trader group!")
        return
    groups["trader"].append({"id": chat.id, "title": chat.title})
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info("Registered %s as trader group", chat.title)
    await update.message.reply_text(f"Registered {chat.title} as a trader group. Now register a trader username with /register_trader_username <username>.")

async def register_trader_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    if not context.args:
        await update.message.reply_text("Usage: /register_trader_username <username>")
        return
    trader_username = context.args[0].lstrip('@')
    groups = context.bot_data.get("groups", load_groups())
    if chat.id not in [g["id"] for g in groups["trader"]]:
        logger.info("Failed to register trader username @%s: not a trader group", trader_username)
        await update.message.reply_text("This group must be registered as a trader group first with /register_trader_group!")
        return
    groups["trader_accounts"][str(chat.id)] = trader_username
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info("Registered trader username @%s for group %s", trader_username, chat.title)
    await update.message.reply_text(f"Registered @{trader_username} as the trader for {chat.title}.")

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.chat_info = set_chat_context(update.message.chat)
    groups = context.bot_data.get("groups", load_groups())
    merchant_list = "\n".join(f"- {g['title']} (ID: {g['id']}, Appeal ID Start: {g.get('appeal_id_start_pos', 0)}, Length: {g.get('appeal_id_length', 0)})" for g in groups["merchant"]) or "None"
    trader_list = "\n".join(f"- {g['title']} (ID: {g['id']}) @{groups['trader_accounts'].get(str(g['id']), 'No username')}" for g in groups["trader"]) or "None"
    response = f"Merchant Groups:\n{merchant_list}\n\nTrader Groups:\n{trader_list}"
    await update.message.reply_text(response)
    logger.info("Listed groups: Merchant=%s, Trader=%s", len(groups["merchant"]), len(groups["trader"]))

async def define_appeal_id_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    logger.info("Started /define_appeal_id")
    groups = context.bot_data.get("groups", load_groups())
    if not any(g["id"] == chat.id for g in groups["merchant"]):
        await update.message.reply_text("This group must be registered as a merchant group first with /register_merchant!")
        return ConversationHandler.END
    
    await update.message.reply_text("Please send a sample appeal message from this group.")
    return WAITING_FOR_MESSAGE

async def receive_appeal_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    message_text = update.message.text or update.message.caption or ""
    if not message_text.strip():
        await update.message.reply_text("Please send a message with text!")
        return WAITING_FOR_MESSAGE
    
    context.user_data["appeal_message"] = message_text
    logger.info("Received sample appeal message: '%s'", message_text)
    await update.message.reply_text("What’s the appeal_id in this message? Reply with the exact appeal_id.")
    return WAITING_FOR_APPEAL_ID

async def receive_appeal_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    appeal_id = update.message.text.strip()
    sample_message = context.user_data.get("appeal_message", "")
    if not appeal_id or appeal_id not in sample_message:
        await update.message.reply_text("That doesn’t seem to be in the message! Please provide the exact appeal_id from the sample.")
        return WAITING_FOR_APPEAL_ID

    # Calculate character position
    start_pos = sample_message.index(appeal_id)
    appeal_length = len(appeal_id)

    groups = context.bot_data.get("groups", load_groups())
    for group in groups["merchant"]:
        if group["id"] == chat.id:
            group["appeal_id_start_pos"] = start_pos
            group["appeal_id_length"] = appeal_length
            break
    context.bot_data["groups"] = groups
    save_groups(groups)
    logger.info("Defined appeal_id position: start=%s, length=%s based on '%s'", start_pos, appeal_length, appeal_id)
    await update.message.reply_text(f"Set appeal_id position: starts at character {start_pos}, length {appeal_length}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.chat_info = set_chat_context(update.message.chat)
    await update.message.reply_text("Cancelled appeal_id definition.")
    return ConversationHandler.END

define_appeal_id_handler = ConversationHandler(
    entry_points=[CommandHandler("define_appeal_id", define_appeal_id_start)],
    states={
        WAITING_FOR_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_appeal_message)],
        WAITING_FOR_APPEAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_appeal_id)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        logger.info("No message in update, skipping")
        return

    chat = update.message.chat
    logger.chat_info = set_chat_context(chat)
    original_message = update.message.text or update.message.caption or ""
    message_text = original_message.lower()
    message_id = update.message.message_id

    logger.info("Received message: '%s'", message_text)
    logger.debug("Full update: %s", update.to_dict())
    logger.info("Message details - Photo: %s, Document: %s, Video: %s, Animation: %s",
                bool(update.message.photo), bool(update.message.document),
                bool(update.message.video), bool(update.message.animation))

    if message_text.startswith('/'):
        logger.info("Skipping message because it's a command: '%s'", message_text)
        return

    groups = context.bot_data.get("groups", load_groups())
    merchant_group = next((g for g in groups["merchant"] if g["id"] == chat.id), None)
    if not merchant_group:
        logger.info("Skipping message because this is not a merchant group")
        return

    if not message_text.strip():
        logger.info("Message text or caption is empty; prompting user")
        await update.message.reply_text("Please include text (e.g., trader name) with your appeal.")
        return

    # Check for Russian text first (notifications take priority)
    has_russian = any(1040 <= ord(char) <= 1103 for char in original_message)  # Cyrillic range
    appeal_ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", original_message)
    if has_russian and appeal_ids:
        logger.info("Detected notification message with appeal_ids: %s", appeal_ids)
        appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
        for appeal_id in appeal_ids:
            # Find trader group from cache (if previously forwarded as an appeal)
            trader_group_id = next((key.split('_')[0] for key, value in appeals_cache.items() if value["appeal_id"] == appeal_id), None)
            trader_group = next((g for g in groups["trader"] if str(g["id"]) == trader_group_id), None) if trader_group_id else None
            if trader_group:
                forward_text = f"Payment appeal `{appeal_id}`"  # No buttons for notification
                try:
                    if update.message.photo:
                        await context.bot.send_photo(
                            chat_id=trader_group["id"],
                            photo=update.message.photo[-1].file_id,
                            caption=forward_text,
                            parse_mode="MarkdownV2"
                        )
                    elif update.message.document:
                        await context.bot.send_document(
                            chat_id=trader_group["id"],
                            document=update.message.document.file_id,
                            caption=forward_text,
                            parse_mode="MarkdownV2"
                        )
                    elif update.message.video:
                        await context.bot.send_video(
                            chat_id=trader_group["id"],
                            video=update.message.video.file_id,
                            caption=forward_text,
                            parse_mode="MarkdownV2"
                        )
                    elif update.message.animation:
                        await context.bot.send_animation(
                            chat_id=trader_group["id"],
                            animation=update.message.animation.file_id,
                            caption=forward_text,
                            parse_mode="MarkdownV2"
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=trader_group["id"],
                            text=forward_text,
                            parse_mode="MarkdownV2"
                        )
                    logger.info("Sent notification to %s (ID: %s) for appeal %s", trader_group["title"], trader_group["id"], appeal_id)
                except Exception as e:
                    logger.error("Failed to send notification to %s (ID: %s): %s", trader_group["title"], trader_group["id"], e)
                    await update.message.reply_text(f"Failed to send notification for appeal '{appeal_id}': {e}")
        await update.message.reply_text(f"Test: Sent notification for appeal{'s' if len(appeal_ids) > 1 else ''} '{', '.join(appeal_ids)}'")
        return  # Exit after handling as notification

    # Process as appeals if no Russian text
    appeals = []
    lines = original_message.split('\n')
    for line in lines:
        uuid_match = re.match(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s+(.+)", line.strip())
        if uuid_match:
            appeal_id = uuid_match.group(1)
            rest_of_line = uuid_match.group(2).strip()
            message_parts = rest_of_line.split()
            trader_nickname = message_parts[0].lower()  # Take first word as nickname
            if len(message_parts) > 1 and message_parts[1].lower() in ["niro", "eastwood", "gosling"]:  # Handle multi-word nicknames
                trader_nickname += " " + message_parts[1].lower()
            appeals.append((appeal_id, trader_nickname))
            logger.info("Test: Detected appeal_id '%s' with trader nickname '%s'", appeal_id, trader_nickname)

    if appeals:
        appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
        for appeal_id, trader_nickname in appeals:
            matched = False
            for trader_group in groups["trader"]:
                trader_title_lower = trader_group["title"].lower()
                if trader_nickname in trader_title_lower:
                    matched = True
                    logger.info("Matched trader group '%s' for nickname '%s'", trader_group["title"], trader_nickname)
                    keyboard = [[InlineKeyboardButton("Approve", callback_data=f"approve_{chat.id}_{message_id}"),
                                InlineKeyboardButton("Decline", callback_data=f"decline_{chat.id}_{message_id}")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    forward_text = f"Payment appeal `{appeal_id}`"

                    # Store the original appeal_id in context.user_data
                    context.user_data[f"appeal_id_{message_id}"] = appeal_id  # Overwrites for multiple appeals; see notes

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
                        logger.info("Forwarded appeal to %s (ID: %s)", trader_group["title"], trader_group["id"])

                        trader_username = groups["trader_accounts"].get(str(trader_group["id"]), "")
                        appeals_cache[f"{trader_group['id']}_{message_id}"] = {
                            "timestamp": datetime.now().isoformat(),
                            "trader_username": trader_username,
                            "chat_id": trader_group["id"],
                            "appeal_id": appeal_id
                        }
                        context.bot_data["appeals_cache"] = appeals_cache
                        save_appeals_cache(appeals_cache)
                        logger.info("Stored appeal %s in cache for %s", appeal_id, trader_group["title"])
                        await update.message.reply_text(f"Test: Forwarded appeal '{appeal_id}'")
                        break
                    except Exception as e:
                        logger.error("Failed to forward to %s (ID: %s): %s", trader_group["title"], trader_group["id"], e)
                        await update.message.reply_text(f"Failed to send appeal: {e}")
                        break
            if not matched:
                logger.info("No trader group matched for nickname '%s'", trader_nickname)
                await update.message.reply_text(f"No matching trader group found for nickname '{trader_nickname}' in appeal '{appeal_id}'")
        return  # Exit after processing all appeals

    # Existing appeal_id extraction (fallback)
    start_pos = merchant_group.get("appeal_id_start_pos", 0)
    appeal_length = merchant_group.get("appeal_id_length", 0)
    if start_pos + appeal_length <= len(original_message):
        appeal_id = original_message[start_pos:start_pos + appeal_length]
    else:
        appeal_id = None

    if not appeal_id:
        logger.info("Could not extract appeal_id at start_pos=%s, length=%s from message: '%s'", start_pos, appeal_length, original_message)
        await update.message.reply_text(f"Couldn’t find an appeal_id at position (start={start_pos}, length={appeal_length}). Use /define_appeal_id to set it.")
        return

    logger.info("TEST: Extracted appeal_id: '%s' at start_pos=%s, length=%s", appeal_id, start_pos, appeal_length)
    await update.message.reply_text(f"TEST: Extracted appeal_id is '{appeal_id}' from start={start_pos}, length={appeal_length}")

    message_words = message_text.strip().split()
    appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
    matched = False
    for trader_group in groups["trader"]:
        trader_title_lower = trader_group["title"].lower()
        trader_name = trader_title_lower.split(' | trader')[0]
        trader_name_words = trader_name.split()

        if any(word in trader_name_words for word in message_words):
            matched = True
            logger.info("Match found with trader group: %s", trader_group["title"])
            keyboard = [[InlineKeyboardButton("Approve", callback_data=f"approve_{chat.id}_{message_id}"),
                        InlineKeyboardButton("Decline", callback_data=f"decline_{chat.id}_{message_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            forward_text = f"Payment appeal `{appeal_id}`"

            # Store the original appeal_id in context.user_data
            context.user_data[f"appeal_id_{message_id}"] = appeal_id

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
                logger.info("Forwarded appeal to %s (ID: %s)", trader_group["title"], trader_group["id"])

                trader_username = groups["trader_accounts"].get(str(trader_group["id"]), "")
                appeals_cache[f"{trader_group['id']}_{message_id}"] = {
                    "timestamp": datetime.now().isoformat(),
                    "trader_username": trader_username,
                    "chat_id": trader_group["id"],
                    "appeal_id": appeal_id
                }
                context.bot_data["appeals_cache"] = appeals_cache
                save_appeals_cache(appeals_cache)
                logger.info("Stored appeal %s in cache for %s", appeal_id, trader_group["title"])
                await update.message.reply_text(f"Test: Forwarded appeal '{appeal_id}'")
                break
            except Exception as e:
                logger.error("Failed to forward to %s (ID: %s): %s", trader_group["title"], trader_group["id"], e)
                await update.message.reply_text(f"Failed to send appeal: {e}")
                break
    if not matched:
        logger.info("No matching trader group found for this appeal")
        await update.message.reply_text("No matching trader group found.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.chat_info = set_chat_context(query.message.chat)
    data = query.data
    logger.info("Callback received: %s", data)

    trader_username = query.from_user.username or query.from_user.first_name
    action, merchant_chat_id, message_id = data.split("_")
    merchant_chat_id = int(merchant_chat_id)
    trader_chat_id = query.message.chat_id
    response = "approved ✅" if action == "approve" else "declined ❌"  # Add emojis here

    # Retrieve the original appeal_id from context.user_data
    appeal_id = context.user_data.get(f"appeal_id_{message_id}", f"APPEAL_{message_id}")  # Fallback to old format if not found

    file_type = context.user_data.get(f"file_type_{message_id}")
    file_id = context.user_data.get(f"file_id_{message_id}")

    appeal_status = api_manager.get_appeal_status(appeal_id)
    if appeal_status and appeal_status.get("status") != "pending":
        logger.info("Appeal %s already resolved via API: %s", appeal_id, appeal_status["status"])
        await query.answer(f"Appeal already {appeal_status['status']}")
        return

    try:
        await context.bot.send_message(
            chat_id=merchant_chat_id,
            text=f"Trader response for `{appeal_id}`: {response}",
            reply_to_message_id=int(message_id),
            parse_mode="MarkdownV2"
        )
        logger.info("Sent response to merchant group %s", merchant_chat_id)
    except Exception as e:
        logger.error("Failed to send to merchant group %s: %s", merchant_chat_id, e)

    try:
        await context.bot.delete_message(
            chat_id=trader_chat_id,
            message_id=query.message.message_id
        )
        logger.info("Deleted original message in trader group %s", trader_chat_id)
    except Exception as e:
        logger.error("Failed to delete message in trader group %s: %s", trader_chat_id, e)

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
            logger.info("Reposted in trader group with text: '%s'", updated_text)
            
            appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
            appeal_key = f"{trader_chat_id}_{message_id}"
            if appeal_key in appeals_cache:
                del appeals_cache[appeal_key]
                context.bot_data["appeals_cache"] = appeals_cache
                save_appeals_cache(appeals_cache)
                logger.info("Removed closed appeal %s from cache", appeal_key)
            break
        except Exception as e:
            logger.error("Attempt %s/%s failed to repost: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                await asyncio.sleep(2)
            else:
                await context.bot.send_message(chat_id=trader_chat_id, text=f"Failed to repost after {retries} attempts: {e}")

async def remind_traders(context: ContextTypes.DEFAULT_TYPE):
    logger.chat_info = "Reminder Task"
    logger.info("Starting trader reminder task")
    while True:
        try:
            appeals_cache = context.bot_data.get("appeals_cache", load_appeals_cache())
            now = datetime.now()
            reminder_intervals = [timedelta(minutes=1), timedelta(minutes=4), timedelta(minutes=8)]
            
            logger.info("Checking %s cached appeals at %s", len(appeals_cache), now)
            for appeal_key, appeal_data in list(appeals_cache.items()):
                appeal_time = datetime.fromisoformat(appeal_data["timestamp"])
                trader_username = appeal_data["trader_username"]
                chat_id = appeal_data["chat_id"]
                appeal_id = appeal_data["appeal_id"]

                appeal_status = api_manager.get_appeal_status(appeal_id)
                if appeal_status and appeal_status.get("status") != "pending":
                    logger.info("Appeal %s resolved via API: %s", appeal_id, appeal_status["status"])
                    del appeals_cache[appeal_key]
                    context.bot_data["appeals_cache"] = appeals_cache
                    save_appeals_cache(appeals_cache)
                    continue

                time_elapsed = now - appeal_time
                for interval in reminder_intervals:
                    seconds = interval.total_seconds()
                    if time_elapsed >= interval and f"reminded_{seconds}" not in appeal_data:
                        if not trader_username:
                            logger.warning("No trader username for appeal %s in chat %s, skipping", appeal_id, chat_id)
                            continue
                        escaped_username = escape_markdown_v2(f"@{trader_username}")
                        minutes_str = str(seconds / 60).replace(".", "\\.")
                        reminder_text = f"{escaped_username}, reminder: Appeal `{appeal_id}` is still unclosed after {minutes_str} minutes\\."
                        logger.info("Attempting to send reminder: '%s' to %s", reminder_text, chat_id)
                        
                        retries = 3
                        for attempt in range(retries):
                            try:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=reminder_text,
                                    parse_mode="MarkdownV2"
                                )
                                logger.info("Sent reminder for %s to @%s in %s", appeal_id, trader_username, chat_id)
                                appeal_data[f"reminded_{seconds}"] = True
                                appeals_cache[appeal_key] = appeal_data
                                context.bot_data["appeals_cache"] = appeals_cache
                                save_appeals_cache(appeals_cache)
                                break
                            except Exception as e:
                                logger.error("Attempt %s/%s failed: %s", attempt + 1, retries, e)
                                if attempt < retries - 1:
                                    await asyncio.sleep(5)
                                else:
                                    logger.error("All retries exhausted for reminder %s", appeal_id)
        except Exception as e:
            logger.error("Reminder task error: %s", e)
        await asyncio.sleep(60)

async def debug_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.chat_info = set_chat_context(update.message.chat if update.message else update.callback_query.message.chat)
    logger.info("Received update")
    logger.debug("Full update: %s", update.to_dict())