"""Location API.

The app posts a heartbeat here while open. Outside an emergency only the
latest point is kept (used as the GPS fallback); during an emergency the point
is also appended to the live track contacts are watching.
"""
from flask import Blueprint, current_app
from flask_login import current_user, login_required

from app.api import authenticated_user, load_json
from app.extensions import db, limiter
from app.schemas import LocationSchema
from app.services import emergency_engine
from app.services.location_service import Coordinates, remember_location

bp = Blueprint("location", __name__, url_prefix="/api/location")


@bp.post("")
@login_required
@limiter.limit(lambda: current_app.config["SENSOR_RATE_LIMIT"])
def update_location():
    coords = Coordinates.from_payload(load_json(LocationSchema()))
    user = authenticated_user()
    incident = emergency_engine.get_active_incident(user)
    if incident is not None:
        emergency_engine.add_location(incident, user, coords)
    else:
        remember_location(user, coords)
        db.session.commit()
    return {
        "last_location": current_user.last_location_dict(),
        "tracking_incident_id": incident.id if incident else None,
    }


@bp.get("/last")
@login_required
def last_location():
    return {"last_location": current_user.last_location_dict()}
