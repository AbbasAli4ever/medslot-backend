"""Staff accounts and login tokens. No database: the account list is fixed in code.

Tokens are signed and stateless (Django's TimestampSigner): the token carries
the staff email and its signing time, so nothing has to be stored server side.
"""

import hmac
from dataclasses import dataclass

from django.conf import settings
from django.core import signing

TOKEN_SALT = "medslot-auth"


@dataclass(frozen=True)
class StaffUser:
    email: str
    name: str

    # Lets DRF permissions (IsAuthenticated...) treat this object as a logged-in user.
    is_authenticated = True


def _accounts() -> dict[str, tuple[StaffUser, str]]:
    """email -> (user, password). Read from settings so env vars and tests can change it."""
    email = settings.STAFF_EMAIL.lower()
    return {email: (StaffUser(email=email, name="Front Desk"), settings.STAFF_PASSWORD)}


def get_staff(email: str) -> StaffUser | None:
    account = _accounts().get(email.lower())
    return account[0] if account else None


def check_credentials(email: str, password: str) -> StaffUser | None:
    account = _accounts().get(email.strip().lower())
    if account is None:
        return None
    user, expected_password = account
    if not hmac.compare_digest(password.encode(), expected_password.encode()):
        return None
    return user


def issue_token(user: StaffUser) -> str:
    return signing.TimestampSigner(salt=TOKEN_SALT).sign(user.email)


def read_token(token: str) -> str:
    """Return the email in a valid token. Raises SignatureExpired or BadSignature."""
    return signing.TimestampSigner(salt=TOKEN_SALT).unsign(
        token, max_age=settings.AUTH_TOKEN_MAX_AGE
    )
