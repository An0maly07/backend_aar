"""Location API helpers: validation, GPS fallback and map links.

Map links use Google Maps and OpenStreetMap URL schemes, which need no API key,
so alerts work out of the box.
"""
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app

from app.models import LocationSource, User
from app.utils.time import utcnow


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lng: float
    accuracy_m: float | None = None

    @classmethod
    def from_payload(cls, data: dict) -> "Coordinates | None":
        """Build from validated request data; ``None`` when the client had no GPS fix."""
        if data.get("lat") is None or data.get("lng") is None:
            return None
        return cls(lat=data["lat"], lng=data["lng"], accuracy_m=data.get("accuracy_m"))


@dataclass(frozen=True)
class ResolvedLocation:
    coordinates: Coordinates | None
    gps_available: bool
    source: str


def resolve_location(user: User, provided: Coordinates | None) -> ResolvedLocation:
    """Algorithm steps 2-3: use the live GPS fix, else a recent last-known location."""
    if provided is not None:
        return ResolvedLocation(provided, gps_available=True, source=LocationSource.GPS)

    max_age = timedelta(minutes=current_app.config["LOCATION_STALE_MINUTES"])
    if (
        user.last_lat is not None
        and user.last_location_at is not None
        and utcnow() - user.last_location_at <= max_age
    ):
        fallback = Coordinates(user.last_lat, user.last_lng, user.last_accuracy_m)
        return ResolvedLocation(fallback, gps_available=False, source=LocationSource.LAST_KNOWN)

    return ResolvedLocation(None, gps_available=False, source=LocationSource.NONE)


def remember_location(user: User, coords: Coordinates) -> None:
    user.last_lat = coords.lat
    user.last_lng = coords.lng
    user.last_accuracy_m = coords.accuracy_m
    user.last_location_at = utcnow()


def google_maps_link(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lng:.6f}"


def osm_link(lat: float, lng: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lng:.6f}#map=17/{lat:.6f}/{lng:.6f}"
