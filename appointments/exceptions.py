"""API errors and the project-wide DRF exception handler.

Every 4xx body has a human-readable ``detail`` string. Field validation
errors also carry ``errors: {field: [messages]}``, with ``detail`` set to
the first message so the frontend can show it directly.
"""

from rest_framework import status
from rest_framework.exceptions import APIException, NotAuthenticated, NotFound, ValidationError
from rest_framework.views import exception_handler


class BookingRuleError(APIException):
    """A clinic rule was broken (closed day, overlap, past date, ...)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This request breaks a clinic rule."
    default_code = "booking_rule"


class InvalidCredentials(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid email or password."
    default_code = "invalid_credentials"


class AppointmentNotFound(NotFound):
    def __init__(self, appointment_id: int):
        super().__init__(f"Appointment {appointment_id} not found.")


def _first_message(errors) -> str:
    if isinstance(errors, dict):
        return _first_message(next(iter(errors.values()), ""))
    if isinstance(errors, list):
        return _first_message(errors[0]) if errors else ""
    return str(errors)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        errors = response.data
        body = {"detail": _first_message(errors)}
        if isinstance(errors, dict):
            body["errors"] = errors
        response.data = body
    elif isinstance(exc, NotAuthenticated):
        response.data = {"detail": "Please log in to continue."}
    else:
        response.data = {"detail": _first_message(response.data)}
    return response
