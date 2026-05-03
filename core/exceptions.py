from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Response | None:
    """
    Extends the default DRF exception handler to catch Django ValidationErrors
    that would otherwise return a 500 Internal Server Error.
    """
    response = exception_handler(exc, context)

    if response is not None:
        return response

    if isinstance(exc, DjangoValidationError):
        return Response(
            {"error": exc.message if hasattr(exc, "message") else str(exc)},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return None
