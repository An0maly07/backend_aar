"""SOS processing.

Deliberately *not* rate-limited: an emergency must never be throttled. The
engine is idempotent instead, so repeated presses reuse the active incident.
"""
from flask import Blueprint
from flask_login import current_user, login_required

from app.api import authenticated_user, get_owned_or_404, load_json
from app.models import Incident, IncidentTrigger
from app.schemas import LocationSchema, SosCancelSchema, SosTriggerSchema
from app.services import emergency_engine
from app.services.emergency_engine import TriggerResult
from app.services.location_service import Coordinates

bp = Blueprint("sos", __name__, url_prefix="/api/sos")


def trigger_response(result: TriggerResult) -> tuple[dict, int]:
    body = {
        "created": result.created,
        "incident": result.incident.to_dict(),
        "alerts": [alert.to_dict() for alert in result.alerts],
        "warnings": result.warnings,
    }
    return body, 201 if result.created else 200


@bp.post("/trigger")
@login_required
def trigger():
    data = load_json(SosTriggerSchema())
    result = emergency_engine.trigger(
        authenticated_user(), IncidentTrigger.SOS, Coordinates.from_payload(data), note=data.get("note")
    )
    return trigger_response(result)


@bp.get("/active")
@login_required
def active():
    incident = emergency_engine.get_active_incident(current_user)
    return {"incident": incident.to_dict(include_locations=True) if incident else None}


@bp.post("/<int:incident_id>/location")
@login_required
def add_location(incident_id: int):
    incident = get_owned_or_404(Incident, incident_id, "Incident not found.")
    data = load_json(LocationSchema())
    point = emergency_engine.add_location(incident, authenticated_user(), Coordinates.from_payload(data))
    return {"location": point.to_dict(), "incident_id": incident.id}, 201


@bp.post("/<int:incident_id>/cancel")
@login_required
def cancel(incident_id: int):
    incident = get_owned_or_404(Incident, incident_id, "Incident not found.")
    data = load_json(SosCancelSchema())
    alerts = emergency_engine.end_incident(incident, authenticated_user(), data["reason"])
    return {"incident": incident.to_dict(), "alerts": [alert.to_dict() for alert in alerts]}
