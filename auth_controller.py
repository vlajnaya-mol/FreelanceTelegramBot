import datetime
import base64
import database_controller as dc
from oauth2client.client import FlowExchangeError
from httplib2 import Http
from oauth2client.client import OAuth2WebServerFlow, Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from misc import NAME, CLIENT_ID, CLIENT_SECRET, GCP_PROJECT_NAME, GCP_TOPIC_NAME, log_line

# Path to client_secrets.json which should contain a JSON document such as:
#   {
#     "web": {
#       "client_id": "[[YOUR_CLIENT_ID]]",
#       "client_secret": "[[YOUR_CLIENT_SECRET]]",
#       "redirect_uris": [],
#       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#       "token_uri": "https://accounts.google.com/o/oauth2/token"
#     }
#   }
REDIRECT_URI = "https://{}.herokuapp.com/.auth/login/google/callback".format(NAME)
SCOPES = ["https://mail.google.com/",
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/userinfo.profile',
          # Add other requested scopes.
          ]
temp_codes = dict()


def add_code(code):
    update_codes()
    encoded_code = base64.b64encode(code.encode()).decode()[:64]
    temp_codes[encoded_code] = code, datetime.datetime.now() + datetime.timedelta(minutes=10)
    return encoded_code


def get_code(key):
    if key in temp_codes:
        code = temp_codes[key][0]
        del temp_codes[key]
        return code


def update_codes():
    # delete all codes which were added more than 10 min ago
    now = datetime.datetime.now()
    expired = []
    for key, value in temp_codes.items():
        expiration_date = value[1]
        if expiration_date < now:
            expired.append(key)
    for key in expired:
        del temp_codes[key]


class GetCredentialsException(Exception):
    """Error raised when an error occurred while retrieving credentials.

    Attributes:
      authorization_url: Authorization URL to redirect the user to in order to
                         request offline access.
    """

    def __init__(self, authorization_url):
        """Construct a GetCredentialsException."""
        self.authorization_url = authorization_url


class CodeExchangeException(GetCredentialsException):
    """Error raised when a code exchange has failed."""


class NoRefreshTokenException(GetCredentialsException):
    """Error raised when no refresh token has been found."""


class NoUserInfoException(Exception):
    """Error raised when no user info could be retrieved."""


def exchange_code(authorization_code):
    """Exchange an authorization code for OAuth 2.0 credentials.

    Args:
      authorization_code: Authorization code to exchange for OAuth 2.0
                          credentials.
    Returns:
      oauth2client.client.OAuth2Credentials instance.
    Raises:
      CodeExchangeException: an error occurred.
    """
    flow = OAuth2WebServerFlow(client_id=CLIENT_ID,
                               client_secret=CLIENT_SECRET,
                               scope=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    try:
        credentials = flow.step2_exchange(authorization_code)
        return credentials
    except FlowExchangeError as err:
        log_line('An error occurred: ' + str(err))
        raise CodeExchangeException(None)


def get_user_info(credentials):
    """Send a request to the UserInfo API to retrieve the user's information.

    Args:
      credentials: oauth2client.client.OAuth2Credentials instance to authorize the
                   request.
    Returns:
      User information as a dict.
    """
    user_info_service = build(
        serviceName='oauth2', version='v2',
        http=credentials.authorize(Http()))
    user_info = None
    try:
        user_info = user_info_service.userinfo().get().execute()
    except HttpError as e:
        log_line('An error occurred: ' + str(e))
    if user_info and user_info.get('email'):
        return user_info
    else:
        raise NoUserInfoException()


def get_authorization_url():
    """Retrieve the authorization URL.

    Args:
      email_address: User's e-mail address.
      state: State for the authorization URL.
    Returns:
      Authorization URL to redirect the user to.
    """
    flow = OAuth2WebServerFlow(client_id=CLIENT_ID,
                               client_secret=CLIENT_SECRET,
                               scope=SCOPES,
                               redirect_uri=REDIRECT_URI)
    flow.params['access_type'] = 'offline'
    flow.params['approval_prompt'] = 'force'
    return flow.step1_get_authorize_url()


def get_credentials(authorization_code):
    """Retrieve credentials using the provided authorization code.

    This function exchanges the authorization code for an access token and queries
    the UserInfo API to retrieve the user's e-mail address.
    If a refresh token has been retrieved along with an access token, it is stored
    in the application database using the user's e-mail address as key.
    If no refresh token has been retrieved, the function checks in the application
    database for one and returns it if found or raises a NoRefreshTokenException
    with the authorization URL to redirect the user to.

    Args:
      authorization_code: Authorization code to use to retrieve an access token.
    Returns:
      oauth2client.client.OAuth2Credentials instance containing an access and
      refresh token.
    Raises:
      CodeExchangeError: Could not exchange the authorization code.
      NoRefreshTokenException: No refresh token could be retrieved from the
                               available sources.
    """
    try:
        credentials = exchange_code(authorization_code)
        email_address = get_user_info(credentials).get('email')
        log_line("Refresh token:" + str(credentials.refresh_token))
        if credentials.refresh_token is not None:
            store_credentials(email_address, credentials)
            return credentials
        else:
            credentials = get_stored_credentials(email_address)
            if credentials and credentials.refresh_token is not None:
                return credentials
    except CodeExchangeException as err:
        log_line('An error occurred during code exchange.\n')
        # Drive apps should try to retrieve the user and credentials for the current session.
        # If none is available, redirect the user to the authorization URL.
        err.authorization_url = get_authorization_url()
        raise err
    except NoUserInfoException:
        log_line('No user info could be retrieved.\n')
        # No refresh token has been retrieved.
        authorization_url = get_authorization_url()
        raise NoRefreshTokenException(authorization_url)


def authorize_user(code, chat_id):
    creds = get_credentials(code)

    email_address = get_user_info(creds).get('email')

    base_history_id = start_watch(email_address)["historyId"]

    dc.save_user(email_address, chat_id, base_history_id)


def start_watch(email_address):
    service = get_gmail_service(email_address)

    topic_path = "projects/{}/topics/{}".format(GCP_PROJECT_NAME, GCP_TOPIC_NAME)
    gmail_request = {"labelIds": ["UNREAD"],
                     "labelFilterAction": "include",
                     "topicName": topic_path}

    service.users().stop(userId="me").execute()

    watch_res = service.users().watch(userId="me", body=gmail_request).execute()
    log_line("Result of watch : " + str(watch_res))

    return watch_res


def renew_watch(chat_id):
    email_address = dc.get_email_address(chat_id)
    return start_watch(email_address)


def store_credentials(email_address, credentials):
    """Store OAuth 2.0 credentials in the application's database.

    This function stores the provided OAuth 2.0 credentials using the user ID as
    key.

    Args:
      email_address: User's email address.
      credentials: OAuth 2.0 credentials to store.
    Raises:
    """
    json_creds = credentials.to_json().encode()
    log_line("# 1" + str(type(json_creds)))
    log_line("# 2" + str(json_creds))
    dc.store_credentials(email_address, json_creds)
    log_line("Creds stored!")


def get_stored_credentials(email_address):
    """Retrieved stored credentials for the provided user ID.

    Args:
      email_address: User's email address.
    Returns:
      Stored oauth2client.client.OAuth2Credentials if found, None otherwise.
    Raises:
      NotImplemented: This function has not been implemented.
    """
    json_creds = dc.get_credentials(email_address)
    creds = Credentials.new_from_json(json_creds)
    return creds


def get_gmail_service(email_address):
    creds = get_stored_credentials(email_address)
    return build("gmail", "v1", http=creds.authorize(Http()))
