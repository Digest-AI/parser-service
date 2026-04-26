"""
Schema utilities for API documentation
"""

from typing import Any, cast

from drf_spectacular.utils import OpenApiExample, OpenApiResponse
from rest_framework import serializers

from .classes import APIException


class ErrorResponseSerializer(serializers.Serializer[Any]):
    code = serializers.IntegerField(help_text="HTTP status code", read_only=True)
    detail = serializers.CharField(help_text="Error detail/message", read_only=True)
    attr = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Field name or attribute that the error relates to",
        read_only=True,
    )


def errors(*exceptions: type[APIException]) -> dict[int, OpenApiResponse]:
    """
    Helper function to add error response status codes to drf-spectacular responses.

    Args:
      *exceptions: Variable number of HTTP status codes (ints)

    Returns:
      Dict suitable for use in extend_schema responses parameter

    Usage:
      @extend_schema(
        responses={
          200: SuccessSerializer,
          **errors(400, 404, 401),
        }
      )
    """

    result: dict[int, OpenApiResponse] = {}
    for exception in exceptions:
        result[exception.status_code] = OpenApiResponse(
            response=ErrorResponseSerializer,
            description=cast(str, exception.default_detail),
            examples=[
                OpenApiExample(
                    name="Error Response",
                    value={"code": exception.status_code, "detail": "", "attr": None},
                ),
            ],
        )

    return result
