import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from pymongo import MongoClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')  # e.g., mongodb+srv://...
DB_NAME = 'telegram_bot_db'
COLLECTION_NAME = 'media_data'

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# Scheduler for delayed tasks
scheduler = AsyncIOScheduler()

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper functions (replacing Bot.getData, Bot.saveData, Bot.genId)
def gen_id():
    return str(uuid.uuid4())

def save_data(media_id, files):
    collection.insert_one({'media_id': media_id, 'files': files})

def get_data(media_id):
    doc = collection.find_one({'media_id': media_id})
    return doc['files'] if doc else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    params = context.args[0] if context.args else None
    if not params or params == "None":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Start Uploading", callback_data="/upload")]])
        await update.message.reply_text(
            "<b>📤 Welcome to Multi File Sharing Bot!</b>\n\n"
            "With this bot, you can:\n"
            "• Upload <b>multiple photos, videos, documents, stickers, audios, voices, animations</b>.\n"
            "• Get a <b>unique shareable link</b> for your uploaded files.\n"
            "• Share that link anywhere, and anyone can open it to view/download your files.\n\n"
            "⚡ <b>How to use:</b>\n"
            "1. Type <code>/upload</code> to start an upload session.\n"
            "2. Send all your media files one by one.\n"
            "3. When finished, type ✅ to confirm upload.\n"
            "4. You will get a shareable link to your uploaded files.\n\n"
            "⏳ Files shared in chat are <b>auto-deleted after 10 minutes</b> to prevent spam.\n"
            "But don’t worry — you can always restore them using the shareable link.\n\n"
            "🚀 Start sharing your files now!",
            parse_mode="html",
            reply_markup=keyboard
        )
    else:
        media_id = params
        files = get_data(media_id)
        if not files:
            await update.message.reply_text("❌ No media found for this link.")
        else:
            sent_msgs = []
            for f in files:
                m = None
                if f["type"] == "photo":
                    m = await update.message.reply_photo(f["file_id"], caption=f.get("caption", ""))
                elif f["type"] == "video":
                    m = await update.message.reply_video(f["file_id"], caption=f.get("caption", ""))
                elif f["type"] == "audio":
                    m = await update.message.reply_audio(f["file_id"])
                elif f["type"] == "voice":
                    m = await update.message.reply_voice(f["file_id"])
                elif f["type"] == "document":
                    m = await update.message.reply_document(f["file_id"])
                elif f["type"] == "animation":
                    m = await update.message.reply_animation(f["file_id"])
                elif f["type"] == "sticker":
                    m = await update.message.reply_sticker(f["file_id"])
                if m:
                    sent_msgs.append(m.message_id)

            note = await update.message.reply_text(
                "⚠️ <b>Note:</b> Files will be automatically deleted from chat after <b>10 minutes</b> to prevent spam.",
                parse_mode="html",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Join Channel", url="t.me/botnations")]])
            )
            sent_msgs.append(note.message_id)

            # Schedule deletion
            scheduler.add_job(delete_messages, 'interval', seconds=600, args=[update.effective_chat.id, sent_msgs, media_id])

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = ReplyKeyboardMarkup([["✅"]], resize_keyboard=True)
    media_id = gen_id()
    await update.message.reply_text("👉 Send me the media you want to upload. When you are done, type ✅.", reply_markup=keyboard)
    context.user_data['media_id'] = media_id
    context.user_data['files'] = []

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    media_id = context.user_data.get('media_id')
    files = context.user_data.get('files', [])
    keyboard = ReplyKeyboardRemove()

    if update.message.text == "✅":
        if files:
            shareable_link = f"https://t.me/{context.bot.username}?start={media_id}"
            await update.message.reply_text(f"✅ Upload complete!\nShare this link:\n{shareable_link}", reply_markup=keyboard)
            save_data(media_id, files)
        else:
            await update.message.reply_text("❌ No media was uploaded.", reply_markup=keyboard)
        context.user_data.clear()
    else:
        media_entry = None
        if update.message.photo:
            media_entry = {"type": "photo", "file_id": update.message.photo[-1].file_id, "caption": update.message.caption or ""}
        elif update.message.video:
            media_entry = {"type": "video", "file_id": update.message.video.file_id, "caption": update.message.caption or ""}
        elif update.message.audio:
            media_entry = {"type": "audio", "file_id": update.message.audio.file_id}
        elif update.message.voice:
            media_entry = {"type": "voice", "file_id": update.message.voice.file_id}
        elif update.message.document:
            media_entry = {"type": "document", "file_id": update.message.document.file_id}
        elif update.message.animation:
            media_entry = {"type": "animation", "file_id": update.message.animation.file_id}
        elif update.message.sticker:
            media_entry = {"type": "sticker", "file_id": update.message.sticker.file_id}

        if media_entry:
            files.append(media_entry)
            await update.message.reply_text("✅ Media saved. Send more or type ✅ to finish.")
        else:
            await update.message.reply_text("❌ Unsupported input. Please send media files only.")

        context.user_data['files'] = files

async def delete_messages(chat_id, msg_ids, media_id):
    bot = Application.builder().token(BOT_TOKEN).build().bot  # Get bot instance
    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    await bot.send_message(
        chat_id=chat_id,
        text="🗑️ Your files have been deleted from chat after 10 minutes.\nClick below to restore them.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Restore Files", url=f"https://t.me/{bot.username}?start={media_id}")]])
    )

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("upload", upload))
    application.add_handler(CallbackQueryHandler(upload, pattern="^/upload$"))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_media))

    scheduler.start()
    application.run_polling()

if __name__ == '__main__':
    main()
