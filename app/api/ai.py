"""AI Detection -> Risk Analysis.

Phones (shake / fall detection) and, later, the ESP32 wearable post sensor
windows here. The response tells the client what to do: nothing, ask the user
"are you safe?", or that an emergency alert has been raised.
"""
from flask import Blueprint, current_app, request
from flask_login import current_user, login_required

from app.api import authenticated_user, get_owned_or_404, load_json
from app.errors import Unprocessable
from app.extensions import db, limiter
from app.models import RiskAssessment
from app.schemas import PaginationSchema, RiskResponseSchema, SensorReadingSchema
from app.services.risk import assessment as risk

bp = Blueprint("ai", __name__, url_prefix="/api/ai")

_ASSESSMENT_STATUSES = {"no_action", "awaiting_user", "confirmed_safe", "escalating", "escalated"}


def _body(assessment: RiskAssessment, result) -> tuple[dict, int]:
    body = {"assessment": assessment.to_dict(), "incident": None, "alerts": [], "warnings": []}
    if result is not None:
        body.update(incident=result.incident.to_dict(), alerts=[a.to_dict() for a in result.alerts],
                    warnings=result.warnings)
    return body, 201 if result is not None and result.created else 200


@bp.post("/assess")
@login_required
@limiter.limit(lambda: current_app.config["SENSOR_RATE_LIMIT"])
def assess():
    reading = load_json(SensorReadingSchema())
    assessment, result = risk.assess(authenticated_user(), reading)
    return _body(assessment, result)


@bp.post("/assessments/<int:assessment_id>/respond")
@login_required
def respond(assessment_id: int):
    assessment = get_owned_or_404(RiskAssessment, assessment_id, "Risk check not found.")
    safe = load_json(RiskResponseSchema())["safe"]
    result = risk.respond(authenticated_user(), assessment, safe)
    db.session.refresh(assessment)
    return _body(assessment, result)


@bp.get("/assessments")
@login_required
def list_assessments():
    args = PaginationSchema().load(request.args)
    query = db.select(RiskAssessment).where(RiskAssessment.user_id == current_user.id)
    if args["status"]:
        if args["status"] not in _ASSESSMENT_STATUSES:
            raise Unprocessable("Unknown status filter.", details={"status": sorted(_ASSESSMENT_STATUSES)})
        query = query.where(RiskAssessment.status == args["status"])
    page = db.paginate(query.order_by(RiskAssessment.created_at.desc()), page=args["page"],
                       per_page=args["per_page"], error_out=False)
    return {"assessments": [a.to_dict() for a in page.items], "page": page.page, "total": page.total}


@bp.get("/model-info")
@login_required
def model_info():
    cfg = current_app.config
    return {
        **current_app.extensions["risk_scorer"].info(),
        "policy": {
            "low": f"score < {cfg['RISK_MEDIUM_THRESHOLD']} -> no action",
            "medium": f"score >= {cfg['RISK_MEDIUM_THRESHOLD']} -> ask user "
                      f"({cfg['RISK_CONFIRM_WINDOW_SECONDS']}s to respond, then auto-alert)",
            "high": f"score >= {cfg['RISK_HIGH_THRESHOLD']} -> emergency alert",
        },
    }
