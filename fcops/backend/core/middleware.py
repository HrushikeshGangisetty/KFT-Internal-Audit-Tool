"""Thread-local storage of the acting user so audit logging can be a
cross-cutting concern rather than being wired into every endpoint."""
import threading

_state = threading.local()


def set_actor(user):
    _state.actor = user


def get_actor():
    return getattr(_state, "actor", None)


def clear_actor():
    _state.actor = None


class CurrentActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # DRF authenticates lazily inside the view, so request.user here may be
        # anonymous. We store the request and resolve the user at write time.
        set_actor(None)
        _state.request = request
        try:
            response = self.get_response(request)
        finally:
            clear_actor()
            _state.request = None
        return response


def get_request():
    return getattr(_state, "request", None)


def resolve_actor():
    actor = get_actor()
    if actor is not None and getattr(actor, "is_authenticated", False):
        return actor
    request = get_request()
    if request is not None:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
    return None
