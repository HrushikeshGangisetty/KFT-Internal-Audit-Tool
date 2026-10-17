"""Login lockout (WP2): a per-username and a per-IP failure counter in the
Django cache. Either reaching ``LOGIN_FAILURE_LIMIT`` locks login for
``LOGIN_LOCKOUT_SECONDS`` from the last failure.

ponytail: the default cache is per process; with several server processes
configure a shared cache (database or Redis) so the counters are shared.
"""
from django.conf import settings
from django.core.cache import cache


def _keys(username, ip):
    return [f"login-fail:user:{(username or '').lower()}", f"login-fail:ip:{ip}"]


def is_locked(username, ip):
    return any((cache.get(k) or 0) >= settings.LOGIN_FAILURE_LIMIT
               for k in _keys(username, ip))


def record_failure(username, ip):
    for key in _keys(username, ip):
        count = (cache.get(key) or 0) + 1
        cache.set(key, count, settings.LOGIN_LOCKOUT_SECONDS)


def clear(username, ip):
    # Only the username counter: one success must not unlock a guessing IP.
    cache.delete(_keys(username, ip)[0])
