"""Track Incident: incident history with the live track and alert audit trail."""
from flask import Blueprint, request
from flask_login import current_user, login_required

from app.api import get_owned_or_404
from app.errors import Unprocessable
from app.extensions import db
from app.models import Incident, IncidentStatus
from app.schemas import PaginationSchema

bp = Blueprint("incidents", __name__, url_prefix="/api/incidents")


@bp.get("")
@login_required
def list_incidents():
    args = PaginationSchema().load(request.args)
    query = db.select(Incident).where(Incident.user_id == current_user.id)
    if args["status"]:
        if args["status"] not in IncidentStatus.ALL:
            raise Unprocessable("Unknown status filter.", details={"status": list(IncidentStatus.ALL)})
        query = query.where(Incident.status == args["status"])
    page = db.paginate(query.order_by(Incident.started_at.desc()), page=args["page"],
                       per_page=args["per_page"], error_out=False)
    return {
        "incidents": [incident.to_dict() for incident in page.items],
        "page": page.page,
        "per_page": page.per_page,
        "total": page.total,
        "pages": page.pages,
    }


@bp.get("/<int:incident_id>")
@login_required
def get_incident(incident_id: int):
    incident = get_owned_or_404(Incident, incident_id, "Incident not found.")
    return {"incident": incident.to_dict(include_locations=True, include_alerts=True)}


@bp.get("/<int:incident_id>/alerts")
@login_required
def incident_alerts(incident_id: int):
    incident = get_owned_or_404(Incident, incident_id, "Incident not found.")
    return {"alerts": [alert.to_dict() for alert in incident.alerts]}
