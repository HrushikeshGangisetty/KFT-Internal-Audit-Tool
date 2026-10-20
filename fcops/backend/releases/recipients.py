"""Recipient sources (WP12).

Only the synthetic source is enabled until the signup API contract is
approved (``SIGNUP_API_ENABLED``). A source failure is an error, never an
empty or partial list that looks complete, and there is no fallback to any
other address list.
"""
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone


@dataclass
class RecipientFetch:
    source: str
    synthetic: bool
    fetched_at: object
    recipients: list = field(default_factory=list)
    errors: list = field(default_factory=list)


class SyntheticRecipientSource:
    """Clearly fake addresses at example.invalid, labelled SYNTHETIC."""
    name = "synthetic"
    SEGMENTS = {"pilot-testers": 3, "all-gcs-users": 8,
                # Demonstrates the failure state end to end.
                "simulate-failure": None}

    def segments(self):
        return list(self.SEGMENTS)

    def fetch_eligible(self, segment):
        fetch = RecipientFetch(self.name, True, timezone.now())
        if segment not in self.SEGMENTS:
            fetch.errors.append(f"Unknown segment '{segment}'.")
        elif self.SEGMENTS[segment] is None:
            fetch.errors.append("Simulated recipient source failure.")
        else:
            fetch.recipients = [
                {"id": f"synthetic-{i:03d}", "email": f"gcs-user-{i:03d}@example.invalid",
                 "name": f"SYNTHETIC recipient {i}"}
                for i in range(1, self.SEGMENTS[segment] + 1)]
        return fetch


class SignupApiRecipientSource:
    """Placeholder: the signup API contract has not been received, so no
    request shape, field names or credentials are assumed here."""
    name = "signup_api"

    def segments(self):
        return []

    def fetch_eligible(self, segment):
        return RecipientFetch(self.name, False, timezone.now(), errors=[
            "The signup API integration is not implemented: its contract is pending."])


def get_source():
    return (SignupApiRecipientSource() if settings.SIGNUP_API_ENABLED
            else SyntheticRecipientSource())


def validate(fetch):
    """Treat every external field as untrusted: one bad row fails the fetch."""
    seen = set()
    for row in fetch.recipients:
        rid, email = str(row.get("id") or ""), str(row.get("email") or "")
        try:
            validate_email(email)
        except ValidationError:
            fetch.errors.append(f"Recipient {rid or '?'} has an invalid email address.")
            continue
        if not rid or rid in seen:
            fetch.errors.append(f"Recipient id '{rid}' is missing or repeated.")
        seen.add(rid)
    return fetch
