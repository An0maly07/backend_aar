"""Phone number normalisation to E.164 (e.g. ``+919876543210``)."""
import re

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_STRIP = re.compile(r"[\s\-().]")


def normalize_phone(raw: str, default_country_code: str = "+91") -> str:
    """Return ``raw`` in E.164 form or raise ``ValueError``.

    Local 10-digit numbers (and the trunk-prefixed ``0XXXXXXXXXX`` form) get the
    default country code, so Indian users can type numbers the way they usually do.
    """
    value = _STRIP.sub("", raw or "")
    if value.startswith("00"):
        value = "+" + value[2:]
    elif not value.startswith("+"):
        if len(value) == 11 and value.startswith("0"):
            value = value[1:]
        value = default_country_code + value
    if not _E164.match(value):
        raise ValueError("Enter a valid phone number, e.g. +919876543210.")
    return value
