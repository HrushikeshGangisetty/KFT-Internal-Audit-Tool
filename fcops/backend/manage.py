#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys

# Checked before anything else is imported so that running on an unsupported
# interpreter produces a useful message instead of a syntax or import error
# from inside a dependency. Django 5.2, DRF 3.18, django-filter and
# python-dotenv all require Python >= 3.10.
MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    sys.exit(
        f"\nThis project needs Python {'.'.join(map(str, MINIMUM_PYTHON))} or newer "
        f"(3.12 recommended).\nYou are running Python {sys.version.split()[0]} "
        f"from {sys.executable}.\n\n"
        "Install a supported Python, then recreate the virtual environment:\n"
        "  Windows:  py -3.12 -m venv .venv && .venv\\Scripts\\activate\n"
        "  macOS/Linux:  python3.12 -m venv .venv && source .venv/bin/activate\n"
        "  pip install -r requirements.txt\n\n"
        "See the 'Python version' section of README.md for details.\n"
    )


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
