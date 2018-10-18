import os
import sys

BOT_USERNAME = os.environ.get("BOT_USERNAME")
TOKEN = os.environ.get("TOKEN")
NAME = os.environ.get("NAME")
PORT = os.environ.get("PORT")
GCP_PROJECT_NAME = os.environ.get("GCP_PROJECT_NAME")
GCP_TOPIC_NAME = os.environ.get("GCP_TOPIC_NAME")
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
DB_KEY = str.encode(os.environ.get("DB_KEY"))
DATABASE_URL = os.environ["DATABASE_URL"]
SERVICE_NAME = os.environ["SERVICE_NAME"]


def log_line(message):
    sys.stdout.write(message + "\n")
