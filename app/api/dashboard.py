"""Safety Dashboard: everything the home screen needs in one call."""
from flask import Blueprint
from flask_login import current_user, login_required

from app.extensions import db
from app.models import AssessmentStatus, Incident, RiskAssessment
from app.services.emergency_engine import get_active_incident

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("")
@login_required
def dashboard():
    active = get_active_incident(current_user)
    pending_check = db.session.scalars(
        db.select(RiskAssessment)
        .where(RiskAssessment.user_id == current_user.id, RiskAssessment.status == AssessmentStatus.AWAITING_USER)
        .order_by(RiskAssessment.created_at.desc())
    ).first()
    recent = db.session.scalars(
        db.select(Incident).where(Incident.user_id == current_user.id).order_by(Incident.started_at.desc()).limit(5)
    ).all()
    contacts = current_user.contacts
    return {
        "user": current_user.to_dict(),
        "contacts_count": len(contacts),
        "ready": bool(contacts),
        "active_incident": active.to_dict() if active else None,
        "pending_risk_check": pending_check.to_dict() if pending_check else None,
        "recent_incidents": [incident.to_dict() for incident in recent],
        "trigger_phrases": [p.phrase for p in current_user.trigger_phrases],
    }
