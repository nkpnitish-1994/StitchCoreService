"""Stable client-facing errors for the versioned REST API."""
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class InvalidStatusTransition(APIException):
    status_code = 400
    default_code = "invalid_status_transition"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, ValidationError):
        code = "validation_error"
        message = "Please correct the supplied fields."
        fields = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
    else:
        code = getattr(exc, "default_code", {403: "permission_denied", 404: "not_found"}.get(response.status_code, "api_error"))
        message = str(response.data.get("detail", "Request failed."))
        fields = {}
    response.data = {"code": code, "message": message, "fields": fields}
    return response


class ProviderUnavailable(APIException):
    status_code = 503
    default_code = "provider_unavailable"
    default_detail = "Phone sign-in is not configured for this environment."
