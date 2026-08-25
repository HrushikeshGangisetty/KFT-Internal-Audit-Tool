from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

# Supabase's pooler refuses new clients once the pool is full. Surfacing the
# raw psycopg2 text as a 500 tells the user nothing useful.
POOL_EXHAUSTED_MARKERS = ("max clients reached", "EMAXCONNSESSION",
                          "too many connections", "MaxClientsInSessionMode")


class WorkflowError(Exception):
    """Raised when a domain/workflow rule is violated (invalid transition,
    missing prerequisite, forbidden state change)."""

    def __init__(self, message, code="workflow_error"):
        self.message = message
        self.code = code
        super().__init__(message)


def api_exception_handler(exc, context):
    if isinstance(exc, OperationalError):
        message = str(exc)
        if any(marker in message for marker in POOL_EXHAUSTED_MARKERS):
            return Response(
                {"detail": "The database connection pool is full, so this request "
                           "could not be served. Restart the API server to release "
                           "connections, and see README -> Connection limits.",
                 "code": "db_pool_exhausted"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(
            {"detail": "The database is unreachable. Check the API server logs.",
             "code": "db_unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, WorkflowError):
        return Response({"detail": exc.message, "code": exc.code},
                        status=status.HTTP_409_CONFLICT)
    if isinstance(exc, DjangoValidationError):
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return exception_handler(exc, context)
