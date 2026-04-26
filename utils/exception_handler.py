import sys
import traceback
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status as http_status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _extract_error_detail(detail_value: Any) -> str:
    """Extract error detail string from various formats"""
    if isinstance(detail_value, list):
        if len(detail_value) > 0:
            # Get first error
            first_item = detail_value[0]
            # Handle ErrorDetail objects
            if hasattr(first_item, "__str__"):
                return str(first_item)
            return str(first_item)
        return "validation_error"
    elif isinstance(detail_value, dict):
        # If it's a dict, try to get the first value
        if detail_value:
            first_key = next(iter(detail_value.keys()))
            return _extract_error_detail(detail_value[first_key])
        return "validation_error"
    else:
        # Handle ErrorDetail objects
        if hasattr(detail_value, "__str__"):
            return str(detail_value)
        return str(detail_value)


def _extract_error_attr(exc: Any, detail_value: Any) -> str | None:
    """Extract attribute/field name from exception"""
    # First, check if exception has explicit attr attribute
    if hasattr(exc, "attr") and exc.attr is not None:
        return cast(str, exc.attr)

    # Check if detail is a dict with explicit attr field
    if isinstance(detail_value, dict) and "attr" in detail_value:
        return cast(str, detail_value["attr"])

    # For ValidationError with dict detail, use the first key as attr
    if isinstance(detail_value, dict):
        first_key = next(iter(detail_value.keys()))
        # Skip if it's a special key
        if first_key not in ["non_field_errors", "detail"]:
            return cast(str, first_key)

    return None


def exception_handler(exc: Any, context: Any) -> Response:
    """
    Custom exception handler that formats errors consistently.

    Returns errors in format: {code: int, detail: str, attr: str | None}
    """
    # Call REST framework's default exception handler first
    response = drf_exception_handler(exc, context)

    # Determine the status code early
    status_code: int | None = None

    # Handle Django ValidationError (from models, etc.)
    if isinstance(exc, DjangoValidationError):
        detail = exc.message if hasattr(exc, "message") else str(exc)
        attr = None

        if hasattr(exc, "message_dict"):
            # Django model validation error - get first field error
            first_field = next(iter(exc.message_dict.keys()))
            field_errors = exc.message_dict[first_field]
            if isinstance(field_errors, list) and field_errors:
                detail = field_errors[0]
            else:
                detail = str(field_errors)
            attr = first_field

        status_code = http_status.HTTP_400_BAD_REQUEST
    # If response is None, exception was not handled by DRF
    elif response is None:
        status_code = http_status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        status_code = response.status_code
        # Handle special case where ValidationError has custom status code
        if (
            isinstance(exc, DRFValidationError)
            and hasattr(exc, "code")
            and isinstance(exc.code, int)
        ):
            status_code = exc.code

    if status_code and (settings.DEBUG or status_code >= 500):
        exc_type, exc_value, exc_traceback = sys.exc_info()
        if exc_type and exc_traceback:
            print("\n" + "=" * 80, file=sys.stderr)
            print(f"EXCEPTION: {exc_type.__name__}: {exc}", file=sys.stderr)
            print(f"STATUS CODE: {status_code}", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
            print("=" * 80 + "\n", file=sys.stderr)

    # Handle Django ValidationError (from models, etc.)
    if isinstance(exc, DjangoValidationError):
        return Response(
            {"code": http_status.HTTP_400_BAD_REQUEST, "detail": str(detail), "attr": attr},
            status=http_status.HTTP_400_BAD_REQUEST,
        )

    # If response is None, exception was not handled by DRF
    if response is None:
        return Response(
            {
                "code": http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                "detail": "internal_server_error",
                "attr": None,
            },
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Get the status code from response (already determined above for traceback)

    # Extract detail and attr
    detail = ""
    attr = None

    if hasattr(exc, "detail"):
        detail = _extract_error_detail(exc.detail)
        attr = _extract_error_attr(exc, exc.detail)
    else:
        detail = str(exc)

    # Final fallback for detail
    if not detail or not detail.strip():
        detail = "error"

    return Response({"code": status_code, "detail": str(detail), "attr": attr}, status=status_code)
