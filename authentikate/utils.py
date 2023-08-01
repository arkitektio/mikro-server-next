from authentikate.structs import Auth
from authentikate.decode import decode_token
from authentikate.settings import get_settings
import re
import logging
from authentikate.expand import expand_token

logger = logging.getLogger(__name__)


def authenticate_token(token: str) -> Auth:
    """
    Authenticate a token and return the auth context
    (containing user, app and scopes)

    """

    settings = get_settings()

    decoded = decode_token(token, settings.algorithms, settings.public_key)
    return expand_token(decoded, settings.force_client)


jwt_re = re.compile(r"Bearer\s(?P<token>[^\s]*)")


def extract_plain_from_authorization(authorization: str) -> str:
    m = jwt_re.match(authorization)
    if m:
        token = m.group("token")
        return token

    raise ValueError("Not a valid token")


def authenticate_header_or_none(headers: dict) -> Auth | None:
    """
    Authenticate a request and return the auth context
    (containing user, app and scopes)

    """
    authorization = headers.get("authorization", None)
    if not authorization:
        authorization = headers.get("Authorization", None)
        if not authorization:
            logger.info("No Authorization header. Skipping!")
            return None

    try:
        token = extract_plain_from_authorization(authorization)
    except ValueError:
        logger.error("Not a valid token. Skipping!")
        return None

    try:
        return authenticate_token(token)
    except Exception:
        logger.error("Error authenticating token. Skipping!", exc_info=True)
        return None


def authenticate_token_or_none(token: dict) -> Auth | None:
    try:
        return authenticate_token(token)
    except Exception:
        logger.error("Error authenticating token. Skipping!", exc_info=True)
        return None
