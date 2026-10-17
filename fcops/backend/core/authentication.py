from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF's session auth, but unauthenticated requests get 401 (not 403) so
    the frontend can tell "log in again" from "not allowed"."""

    def authenticate_header(self, request):
        return "Session"
