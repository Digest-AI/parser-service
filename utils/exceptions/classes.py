"""
Custom exception classes that support attr parameter
"""

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException as DRFAPIException


class APIException(DRFAPIException):
    """Base custom exception that supports attr parameter"""

    def __init__(
        self, detail: Any | None = None, code: Any | None = None, attr: Any | None = None
    ) -> None:
        super().__init__(detail=detail, code=code)
        self.attr = attr


class BadRequest(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Bad request."
    default_code = "bad_request"


class Unauthorized(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Unauthorized."
    default_code = "unauthorized"


class Forbidden(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Forbidden."
    default_code = "forbidden"


class NotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Not found."
    default_code = "not_found"


class InternalServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Internal server error."
    default_code = "internal_server_error"
