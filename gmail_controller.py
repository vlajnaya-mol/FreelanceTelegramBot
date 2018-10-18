import email
import base64
import datetime
import re
import html2text
import database_controller as dc
import auth_controller as ac
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dateutil.relativedelta import relativedelta
from misc import SERVICE_NAME, log_line


def organize_mime_msg(mime_msg):
    def get_decoded_header(header_name):
        header = mime_msg[header_name]
        decoded = ""
        for value, charset in email.header.decode_header(header):
            if not charset and isinstance(value, bytes):
                charset = "UTF-8"
            decoded += "{}".format(value.decode(charset) if charset else value)
        return decoded

    def get_body(html=True):
        body = ""
        content_type = "text/html" if html else "text/plain"
        for part in mime_msg.walk():
            if "multipart" not in part.get_content_type() and part.get_content_type() == content_type:
                body += "{}\n".format(part.get_payload(decode=True).decode("UTF-8"))
        if html:
            log_line("BODY : " + body)
            body = html2text.html2text(body)
            log_line("PARSED BODY : " + body)
        return body

    updated_msg = MIMEMultipart()
    updated_msg['Subject'] = get_decoded_header("Subject")
    updated_msg['From'] = get_decoded_header("From")
    updated_msg['To'] = get_decoded_header("To")

    content = get_body()
    content = re.sub("\[\]\([^)]*\)", "", content)
    updated_msg.attach(MIMEText(content, "plain"))
    return updated_msg


def get_mime_msg(service, msg_id):
    message = service.users().messages().get(userId="me", id=msg_id,
                                             format="raw").execute()
    msg_bytes = base64.urlsafe_b64decode(message['raw'].encode("UTF-8"))
    return organize_mime_msg(email.message_from_bytes(msg_bytes))


def get_tasks(chat_id):
    email_address = dc.get_email_address(chat_id)
    service = ac.get_gmail_service(email_address)

    before = datetime.date.today().strftime("%Y/%m/%d").replace("/0", "/")
    after = (datetime.date.today() + relativedelta(days=-3)).strftime("%y/%m/%d").replace("/0", "/")
    query = "from:(service@{}) subject:python after:{} before:{}".format(SERVICE_NAME, after, before)

    response = service.users().messages().list(userId="me",
                                               q=query).execute()
    messages = []

    if 'messages' in response:
        messages.extend(response['messages'])

    while 'nextPageToken' in response:
        page_token = response['nextPageToken']
        response = service.users().messages().list(userId="me", q=query,
                                                   pageToken=page_token).execute()
        messages.extend(response['messages'])
    mime_msgs = []
    for m in messages:
        mime_msgs.append(get_mime_msg(service, m["id"]))

    log_line("GF tasks were received!")
    return mime_msgs


def get_new_messages(email_address, start_history_id):
    gmail_service = ac.get_gmail_service(email_address)
    changes = get_changes(email_address, gmail_service, start_history_id)
    messages = get_msgs_from_changes(changes, gmail_service)
    log_line("New messages were received")
    return messages


def get_changes(email_address, gmail_service, start_history_id):
    latest_history = gmail_service.users().history().list(userId="me", startHistoryId=start_history_id).execute()

    dc.change_latest_history_id(email_address, latest_history["historyId"])

    changes = latest_history['history'] if 'history' in latest_history else []
    while 'nextPageToken' in latest_history:
        page_token = latest_history['nextPageToken']
        latest_history = (gmail_service.users().history().list(userId="me",
                                                               startHistoryId=start_history_id,
                                                               pageToken=page_token).execute())
        changes.extend(latest_history['history'])
    return changes


def get_msgs_from_changes(changes, gmail_service):
    messages = list()
    for page in changes:
        if "messagesAdded" in page:
            for message_record in page["messagesAdded"]:
                message_resource = message_record["message"]
                if "UNREAD" in message_resource["labelIds"]:
                    # we should get the message again because message_resource contains too few info
                    messages.append(get_mime_msg(gmail_service, message_resource["id"]))
    return messages
