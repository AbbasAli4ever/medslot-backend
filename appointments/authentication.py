"""DRF authentication via ``Authorization: Bearer <token>``, plus its Swagger scheme."""

from django.core import signing
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .staff import get_staff, read_token

KEYWORD = "Bearer"


class BearerTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).decode(errors="ignore").split()
        if not parts or parts[0].lower() != KEYWORD.lower():
            return None  # No credentials: let permissions decide (public GETs stay open).
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid token. Please log in again.")

        try:
            email = read_token(parts[1])
        except signing.SignatureExpired:
            raise AuthenticationFailed("Your session has expired. Please log in again.")
        except signing.BadSignature:
            raise AuthenticationFailed("Invalid token. Please log in again.")

        user = get_staff(email)
        if user is None:
            raise AuthenticationFailed("Invalid token. Please log in again.")
        return user, parts[1]

    def authenticate_header(self, request):
        # Makes DRF answer 401 (with WWW-Authenticate) instead of 403.
        return KEYWORD


class BearerTokenScheme(OpenApiAuthenticationExtension):
    """Adds the bearer scheme to the OpenAPI schema so Swagger's Authorize button works."""

    target_class = BearerTokenAuthentication
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return build_bearer_security_scheme_object(header_name="AUTHORIZATION", token_prefix=KEYWORD)
