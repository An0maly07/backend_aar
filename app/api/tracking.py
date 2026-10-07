"""Public live-tracking link sent to emergency contacts ("Share live location").

Access is by unguessable token only. Once the emergency ends the link stops
revealing any location, so contacts can't keep following the user afterwards.
"""
from flask import Blueprint, current_app, render_template

from app.errors import NotFound
from app.extensions import db, limiter
from app.models import Incident
from app.utils.time import isoformat

bp = Blueprint("tracking", __name__)

MAX_PATH_POINTS = 500
_limit = limiter.limit(lambda: current_app.config["TRACKING_RATE_LIMIT"])

_CSP = (
    "default-src 'none'; script-src 'self' https://unpkg.com; style-src 'self' https://unpkg.com; "
    "img-src 'self' data: https://unpkg.com https://tile.openstreetmap.org; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def _incident_for(token: str) -> Incident:
    incident = db.session.scalars(db.select(Incident).where(Incident.share_token == token)).first()
    if incident is None:
        raise NotFound("This tracking link is invalid.")
    return incident


@bp.get("/track/<token>")
@_limit
def track_page(token: str):
    _incident_for(token)
    response = current_app.make_response(render_template("track.html", token=token))
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/track/<token>")
@_limit
def track_data(token: str):
    incident = _incident_for(token)
    data = {
        "name": incident.user.first_name,
        "status": incident.status,
        "trigger": incident.trigger,
        "started_at": isoformat(incident.started_at),
        "ended_at": isoformat(incident.ended_at),
        "gps_available": incident.gps_available,
        "emergency_number": current_app.config["EMERGENCY_NUMBER"],
        "latest": None,
        "path": [],
    }
    if incident.is_active:
        points = incident.locations[-MAX_PATH_POINTS:]
        data["latest"] = points[-1].to_dict() if points else None
        data["path"] = [[p.lat, p.lng] for p in points]
    return data
