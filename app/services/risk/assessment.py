"""AI Detection workflow: score sensor data, then act on the blueprint's policy.

Low -> nothing. Medium -> ask the user, who has a short window to answer
before the sweeper escalates automatically. High -> straight to the
Emergency Engine.
"""
import logging
from datetime import timedelta

from flask import current_app

from app.errors import Conflict
from app.extensions import db
from app.models import AssessmentStatus, IncidentTrigger, RiskAction, RiskAssessment, User
from app.services import emergency_engine
from app.services.emergency_engine import TriggerResult
from app.services.location_service import Coordinates, remember_location
from app.services.risk.features import build_features
from app.services.risk.policy import decide
from app.utils.time import utcnow

log = logging.getLogger(__name__)


def assess(user: User, reading: dict) -> tuple[RiskAssessment, TriggerResult | None]:
    cfg = current_app.config
    scorer = current_app.extensions["risk_scorer"]
    features = build_features(reading, user.baseline_heart_rate or cfg["BASELINE_HEART_RATE"])
    score = scorer.score(features)
    level, action = decide(score, cfg["RISK_MEDIUM_THRESHOLD"], cfg["RISK_HIGH_THRESHOLD"])

    coords = Coordinates.from_payload(reading)
    if coords is not None:
        remember_location(user, coords)

    pending = _pending_for(user)
    if action == RiskAction.ASK_USER and pending is not None:
        # Sensors stream continuously; keep one open question instead of spamming the user.
        if score > pending.score:
            pending.score, pending.features, pending.level = score, features, level
        db.session.commit()
        return pending, None

    active = emergency_engine.get_active_incident(user)
    assessment = RiskAssessment(
        user=user, features=features, score=score, scorer=scorer.source, level=level, action=action,
        lat=coords.lat if coords else None, lng=coords.lng if coords else None,
        accuracy_m=coords.accuracy_m if coords else None,
    )
    if action == RiskAction.NO_ACTION:
        assessment.status, assessment.resolved_at = AssessmentStatus.NO_ACTION, utcnow()
    elif active is not None:
        # Already in an emergency: nothing new to raise, just link the reading to it.
        assessment.status, assessment.incident_id, assessment.resolved_at = (
            AssessmentStatus.ESCALATED, active.id, utcnow())
    elif action == RiskAction.ASK_USER:
        assessment.status = AssessmentStatus.AWAITING_USER
        assessment.expires_at = utcnow() + timedelta(seconds=cfg["RISK_CONFIRM_WINDOW_SECONDS"])
    else:
        assessment.status = AssessmentStatus.ESCALATING
    db.session.add(assessment)
    db.session.commit()

    result = None
    if assessment.status == AssessmentStatus.ESCALATING:
        result = _escalate(assessment, user, note=f"Automatic: high risk score {score:.2f}")
        if pending is not None and _transition(pending.id, AssessmentStatus.ESCALATED, incident_id=result.incident.id):
            log.info("Closed pending risk check %s with incident %s", pending.id, result.incident.id)
    return assessment, result


def respond(user: User, assessment: RiskAssessment, safe: bool) -> TriggerResult | None:
    """The user's answer to a Medium-risk "are you safe?" check."""
    if safe:
        if not _transition(assessment.id, AssessmentStatus.CONFIRMED_SAFE):
            _raise_already_resolved(assessment)
        return None
    if not _transition(assessment.id, AssessmentStatus.ESCALATING, resolved=False):
        _raise_already_resolved(assessment)
    return _escalate(assessment, user, note="User reported they are not safe during a risk check")


def sweep_expired_assessments() -> int:
    """Escalate Medium-risk checks the user did not answer in time."""
    expired_ids = db.session.scalars(
        db.select(RiskAssessment.id).where(
            RiskAssessment.status == AssessmentStatus.AWAITING_USER,
            RiskAssessment.expires_at <= utcnow(),
        )
    ).all()
    escalated = 0
    for assessment_id in expired_ids:
        # Atomic claim: if the user answers at the same moment, only one side wins.
        if not _transition(assessment_id, AssessmentStatus.ESCALATING, resolved=False):
            continue
        assessment = db.session.get(RiskAssessment, assessment_id)
        try:
            _escalate(assessment, assessment.user, note="Automatic: no response to risk check")
            escalated += 1
        except Exception:
            log.exception("Escalating risk check %s failed; will retry", assessment_id)
            db.session.rollback()
            _transition(assessment_id, AssessmentStatus.AWAITING_USER, expected=AssessmentStatus.ESCALATING,
                        resolved=False)
    return escalated


def _escalate(assessment: RiskAssessment, user: User, note: str) -> TriggerResult:
    coords = (Coordinates(assessment.lat, assessment.lng, assessment.accuracy_m)
              if assessment.lat is not None else None)
    result = emergency_engine.trigger(user, IncidentTrigger.AI, coords, risk_score=assessment.score, note=note)
    assessment.status = AssessmentStatus.ESCALATED
    assessment.incident_id = result.incident.id
    assessment.resolved_at = utcnow()
    db.session.commit()
    return result


def _pending_for(user: User) -> RiskAssessment | None:
    return db.session.scalars(
        db.select(RiskAssessment)
        .where(RiskAssessment.user_id == user.id, RiskAssessment.status == AssessmentStatus.AWAITING_USER)
        .order_by(RiskAssessment.created_at.desc())
    ).first()


def _transition(assessment_id: int, new_status: str, *, expected: str = AssessmentStatus.AWAITING_USER,
                resolved: bool = True, incident_id: int | None = None) -> bool:
    """Compare-and-set the status in one UPDATE so concurrent actors can't double-act."""
    values = {"status": new_status}
    if resolved:
        values["resolved_at"] = utcnow()
    if incident_id is not None:
        values["incident_id"] = incident_id
    result = db.session.execute(
        db.update(RiskAssessment)
        .where(RiskAssessment.id == assessment_id, RiskAssessment.status == expected)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    return result.rowcount == 1


def _raise_already_resolved(assessment: RiskAssessment) -> None:
    db.session.refresh(assessment)
    raise Conflict(
        "This risk check has already been resolved.",
        code="assessment_resolved",
        details={"status": assessment.status, "incident_id": assessment.incident_id},
    )
