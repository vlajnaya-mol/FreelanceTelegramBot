import logging
import json
import base64
import gmail_controller as gc
import auth_controller as ac
import database_controller as dc
import sys
from bot_controller import MyBot
from misc import PORT, TOKEN, BOT_USERNAME, log_line
from flask import Flask, request

# TODO: doubling messages sometimes
# TODO: not full GF mails
# TODO: diff authorize
# TODO: renew watch every day
# TODO: rename email_chats table?
# TODO: History records are typically available for at least one week and often longer.
# DONE: force approval for login?

SCOPE = "https://mail.google.com/"

app = Flask(__name__)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.INFO)

bot = MyBot()


@app.route("/")
def hello():
    return "<html><body><h1>whatsup?</h1></body></html>"


@app.route("/.auth/login/google/callback", methods=["GET"])
def login():
    code = request.args.get("code")
    encoded_code = ac.add_code(code)
    redirect = ("<html><head>"
                + "<meta http-equiv=\"refresh\" content=\"0; "
                + "url=https://telegram.me/{}?start={}".format(BOT_USERNAME, encoded_code)
                + "\" /></head></html>")
    return redirect


@app.route("/" + TOKEN, methods=["POST"])
def webhook():
    msg = request.get_json(force=True)
    bot.process_msg(msg)
    log_line("Message was processed")
    return "Hello there!"


@app.route("/notify", methods=["POST"])
def receive_email_notification():
    response = request.get_json(force=True)
    encrypted_message_data = response["message"]["data"]
    message_data = json.loads(base64.b64decode(encrypted_message_data))
    try:
        process_email_notification(message_data)
    except dc.NotFoundException:
        log_line("FAILED TO RECEIVE NOTIFICATION!")
        return "Unauthorized", 401
    return "OK", 200


def process_email_notification(message_data):
    email_address = message_data["emailAddress"]
    start_history_id = dc.get_latest_historyId(email_address)
    chat_id = dc.get_chat_id(email_address)

    bot.send_message(chat_id=chat_id,
                     text="You have received this historyId : " + str(message_data["historyId"]))
    # bot.send_message(chat_id=chat_id,
    #                 text="You have received these changes : " + str(changes)[:4000])

    messages = gc.get_new_messages(email_address, start_history_id)

    for mime_msg in messages:
        bot.send_mime_msg(chat_id=chat_id,
                          mime_msg=mime_msg)

    log_line("Email notification was processed!")


app.run(host="0.0.0.0",
        port=PORT,
        debug=True)
