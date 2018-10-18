import psycopg2
from misc import DATABASE_URL, DB_KEY, log_line
from Crypto.Cipher import AES


class NotFoundException(Exception):
    """Some important data was not found in the database"""

    def __init__(self, value, column, table):
        msg = "{} was not found in {} column of {} table!\n".format(value, column, table)
        super().__init__(msg)
        log_line(msg)


class CipherException(Exception):
    """Error raised when a encryption/decryption has failed."""


def encrypt(data):
    log_line("Creds try encript!")
    cipher = AES.new(DB_KEY, AES.MODE_EAX)
    nonce = cipher.nonce
    cipher_text, tag = cipher.encrypt_and_digest(data)

    log_line("Creds encrypt_and_digest!")
    return cipher_text, tag, nonce


def decrypt(cipher_text, tag, nonce):
    cipher = AES.new(DB_KEY, AES.MODE_EAX, nonce=nonce)
    plaintext = cipher.decrypt(cipher_text)
    try:
        cipher.verify(tag)
        log_line("Decryption went fine!")
        return plaintext
    except ValueError:
        log_line("Decryption went wrong!")
        raise CipherException


def get_database_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except:
        log_line("Unable to connect to database!")


def exec_data_manipulation_query(query):
    con = get_database_connection()
    cur = con.cursor()
    cur.execute(query)
    con.commit()
    cur.close()
    con.close()


def exec_select_query(query):
    con = get_database_connection()
    cur = con.cursor()
    cur.execute(query)
    res = cur.fetchone()
    con.commit()
    cur.close()
    con.close()
    return res


def get_latest_historyId(email_address):
    historyIds = exec_select_query("SELECT last_historyId FROM email_historyIds WHERE email = \'{}\'"
                                   .format(email_address))
    if historyIds:
        return historyIds[0]
    raise NotFoundException(email_address, "email", "email_historyIds")


def get_chat_id(email_address):
    chat_ids = exec_select_query("SELECT chat FROM email_chats WHERE email = \'{}\'"
                                 .format(email_address))
    if chat_ids:
        return chat_ids[0]
    raise NotFoundException(email_address, "email", "email_chats")


def get_credentials(email_address):
    creds = exec_select_query("SELECT cipher_text, tag, nonce FROM email_credentials WHERE email = \'{}\'"
                              .format(email_address))
    if creds and len(creds) == 3:
        return decrypt(*creds)
    raise NotFoundException(email_address, "email", "email_credentials")


def store_credentials(email_address, credentials):
    log_line("Creds try store!")
    cipher_text, tag, nonce = encrypt(credentials)
    cipher_text, tag, nonce = [psycopg2.Binary(data) for data in (cipher_text, tag, nonce)]
    log_line("Creds encrypted!")
    try:
        exec_data_manipulation_query(
            "INSERT INTO email_credentials (email, cipher_text, tag, nonce) VALUES (\'{}\', {}, {}, {})"
                .format(email_address, cipher_text, tag, nonce))
        log_line("User " + email_address + " was successfully added to email_credentials table!")
    except psycopg2.IntegrityError:
        log_line("email_credentials already contains " + email_address + " key!")
    except Exception as e:
        log_line(str(e) + " key!")


def change_latest_history_id(email_address, new_historyId):
    try:
        exec_data_manipulation_query("UPDATE email_historyIds SET last_historyId = {} WHERE email = \'{}\'"
                                     .format(new_historyId, email_address))
    except psycopg2.IntegrityError:
        log_line("Update was failed!")
        raise NotFoundException(email_address, "email", "email_historyIds")


def save_user(email_address, chat_id, base_history_id):
    try:
        exec_data_manipulation_query("INSERT INTO email_chats (email, chat) VALUES (\'{}\', {})"
                                     .format(email_address, chat_id))
        log_line("User " + email_address + " was successfully added to email_chats table!")
    except psycopg2.IntegrityError:
        log_line("email_chats already contains " + email_address + " key!")
    try:
        exec_data_manipulation_query(
            "INSERT INTO email_historyIds (email, base_historyId, last_historyId) VALUES (\'{}\', {}, {})"
                .format(email_address, base_history_id, base_history_id))
        log_line("User " + email_address + " was successfully added to email_historyIds table!")
    except psycopg2.IntegrityError:
        log_line("email_historyIds already contains " + email_address + " key!")


def create_tables():
    try:
        exec_data_manipulation_query(
            "CREATE TABLE email_credentials (email text, cipher_text bytea, tag bytea, nonce bytea, PRIMARY KEY (email))")
        # raise NotImplementedError
        # exec_data_manipulation_query("alter table email_historyIds add primary key ( email )")
        # exec_data_manipulation_query("alter table email_chats add primary key ( email )")
    except psycopg2.ProgrammingError:
        log_line("email_historyIds already exists!")


def get_email_address(chat_id):
    email_addresses = exec_select_query("SELECT email FROM email_chats WHERE chat = {}"
                                        .format(chat_id))
    if email_addresses:
        return email_addresses[0]
    raise NotFoundException(chat_id, "chat", "email_chats")
