import logging, os, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import *
from telegram.ext import *
from readwise import ReadWise
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WISE = ReadWise(os.getenv('READWISE_TOKEN'))
ADMIN = int(os.getenv('ADMIN_USER_ID'))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

FORWARD = range(1)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', 8000), HealthHandler)
    server.serve_forever()

def restricted(func):
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN:
            print(f"Unauthorized access denied for {user_id}.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def url_extracter(entities):
    for ent in entities:
        txt = entities[ent]
        if ent.type == ent.TEXT_LINK:
            return str(ent.url)
        elif ent.type == ent.URL:
            return str(txt)

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Bot for integration with ReadWise api and Telegram. Forward me posts and I will send them to your ReadWise.")

@restricted
async def send_to_readwise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[+] Message from " + str(update.effective_user.id))
    telegram_link = "<a href='https://t.me/" + str(update.message.forward_from_chat.username) + "/" + str(update.message.forward_from_message_id) + "'>Telegram Link</a>"
    note_txt = "from Telegram bot"
    text = update.message.text_html if update.message.caption_html is None else update.message.caption_html
    text = text + "\n\n" + telegram_link
    post_link = url_extracter(update.message.parse_entities())
    from_who = str(update.message.forward_from_chat.username)
    WISE.check_token()
    WISE.highlight(text=text, title=from_who, source_url=telegram_link, highlight_url=post_link, note=note_txt, highlighted_at=str(datetime.now().isoformat()))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Message from %s was highlighted." % from_who)

@restricted
async def prepare_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sending data to Readwise Reader...")
    return FORWARD

@restricted
async def send_to_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_link = "https://t.me/" + str(update.message.forward_from_chat.username) + "/" + str(update.message.forward_from_message_id)
    text = update.message.text_html if update.message.caption_html is None else update.message.caption_html
    WISE.check_token()
    WISE.save(url=telegram_link, html=text, title=str(update.message.forward_from_chat.username) + " " + str(datetime.now().isoformat()), summary=text[:128])
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Saved to Reader.")
    return ConversationHandler.END

@restricted
async def cancel(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Cancelled.")
    return ConversationHandler.END

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler_reader = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^r$"), prepare_reader)],
        states={FORWARD: [MessageHandler((filters.TEXT | filters.ATTACHMENT | filters.PHOTO) & ~filters.COMMAND, send_to_reader)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler_reader)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler((filters.TEXT | filters.ATTACHMENT | filters.PHOTO) & ~filters.COM
