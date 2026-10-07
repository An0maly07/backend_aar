"""Time helpers.

All timestamps are stored as *naive UTC* datetimes, which behaves identically on
SQLite and MySQL, and are serialised as ISO-8601 with a ``Z`` suffix.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat() + "Z"
