import telegram
import auth_controller as ac
import gmail_controller as gc
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from misc import NAME, TOKEN, log_line
from time import sleep


def echo(bot, update):
    update.effective_message.reply_text(update.effective_message.text)
    log_line("Answered!")


def error(bot, update, error_):
    log_line("Update {} caused error {}".format(str(update), str(error_)))


def help_(bot, update):
    chat_id = update.effective_chat.id
    ac.renew_watch(chat_id)
    log_line("Watch was revoked!")


def tasks(bot, update):
    chat_id = update.effective_chat.id
    mime_msgs = gc.get_tasks(chat_id)
    update.effective_message.reply_text("TASK LIST")
    for m in mime_msgs:
        update.effective_message.reply_text(repr_mime_msg(m)[:100])


def start(bot, update, args):
    log_line("Started!")
    if args:
        code = ac.get_code(args[0])
        if not code:
            update.effective_message.reply_text("What does " + ''.join(args) + " mean? Try again please!")
            log_line("Start parameters were wrong!")
            return
        log_line("Bot has received the key!")
        update.effective_message.reply_text("Hello there, Telegram user!")
        ac.authorize_user(code, update.effective_chat.id)
    else:
        # store = oauth_file.Storage(str(update.effective_user.id) + "_token.json")
        authorize_url = ac.get_authorization_url()
        update.effective_message.reply_text(authorize_url)


class MyBot:
    def __init__(self):
        self.bot = telegram.Bot(TOKEN)
        self.codes = dict()
        self.dispatcher = Dispatcher(self.bot, None, workers=0)
        self.add_handlers()
        self.set_webhook()

    def add_handlers(self):
        self.dispatcher.add_handler(CommandHandler("start", start, pass_args=True))
        self.dispatcher.add_handler(CommandHandler("help", help_))
        self.dispatcher.add_handler(CommandHandler("gettasks", tasks))
        self.dispatcher.add_handler(MessageHandler(Filters.text, echo))
        self.dispatcher.add_error_handler(error)

    def process_msg(self, msg):
        update = telegram.update.Update.de_json(msg, self.bot)
        self.dispatcher.process_update(update)

    def send_message(self, chat_id, text):
        self.bot.sendMessage(chat_id=chat_id, text=text, disable_web_page_preview=True)

    def send_mime_msg(self, chat_id, mime_msg):
        text_msg = repr_mime_msg(mime_msg)
        if len(text_msg) > 4096:
            text_msg = "TEXT IS TOO LONG\n\n" + text_msg
            log_line("Mime message was TOO LONG!")
            while len(text_msg) > 0:
                self.bot.sendMessage(chat_id=chat_id, text=text_msg[:4000],
                                     disable_web_page_preview=True, parse_mode=telegram.ParseMode.MARKDOWN)
                text_msg = text_msg[4000:]
        self.bot.sendMessage(chat_id=chat_id, text=text_msg,
                             disable_web_page_preview=True, parse_mode=telegram.ParseMode.MARKDOWN)
        log_line("Mime message was sent!")

    def set_webhook(self):
        if not bool(self.bot.get_webhook_info().url):
            try:
                self.bot.setWebhook("https://{}.herokuapp.com/{}".format(NAME, TOKEN))
                log_line("Webhook was set")
            except telegram.error.RetryAfter:
                log_line("telegram.error.RetryAfter WAS ENCOUNTERED :(")
                sleep(2)
                self.set_webhook()


def repr_mime_msg(msg):
    mail_emoji = "\U00002709"
    body = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body += part.get_payload(decode=True).decode("UTF-8")
    representation = ("From : {}{}\nSubject : {}\n{}\n"
                      .format(mail_emoji, msg["From"], msg["Subject"], body))
    # log_line(representation)
    log_line("Message representation was received!")
    return representation
