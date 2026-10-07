"""The Emergency Engine.

All three triggers from the blueprint (SOS button, verified voice command and
high-risk AI detection) end up here, so an emergency behaves the same way no
matter how it was raised. ``trigger`` follows the SOS algorithm step by step:

    1. User presses SOS (or voice / AI raises it)
    2. Check whether GPS is available
    3. Get current latitude and longitude
    4. Get emergency contacts
    5. Create emergency message
    6. Send alert to emergency contacts
    7. Start location tracking
    8. Store the incident in database
    9. Continue until user cancels emergency mode
"""
import logging
from dataclasses import dataclass, field

from app.errors import Conflict
from app.extensions import db
from app.models import Alert, Incident, IncidentStatus, LocationPoint, LocationSource, User
from app.services import alert_service
from app.services.location_service import Coordinates, remember_location, resolve_location
from app.utils.time import utcnow

log = logging.getLogger(__name__)


@dataclass
class TriggerResult:
    incident: Incident
    created: bool
    alerts: list[Alert] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def get_active_incident(user: User, *, lock: bool = False) -> Incident | None:
    query = db.select(Incident).where(Incident.user_id == user.id, Incident.status == IncidentStatus.ACTIVE)
    if lock:
        query = query.with_for_update()
    return db.session.scalars(query.order_by(Incident.started_at.desc())).first()


def trigger(
    user: User,
    source: str,
    coords: Coordinates | None = None,
    *,
    risk_score: float | None = None,
    note: str | None = None,
) -> TriggerResult:
    # Step 1 - serialise concurrent triggers for this user (row lock on MySQL) and
    # stay idempotent: a second press must not start a second alert storm.
    db.session.execute(db.select(User.id).where(User.id == user.id).with_for_update())
    existing = get_active_incident(user)
    if existing is not None:
        if coords is not None:
            _append_location(existing, user, coords)
            db.session.commit()
        return TriggerResult(existing, created=False,
                             warnings=["An emergency is already active; returning the existing incident."])

    # Steps 2-3 - GPS check, falling back to the last known location.
    resolved = resolve_location(user, coords)
    warnings: list[str] = []
    if resolved.coordinates is None:
        warnings.append("No location available. Contacts are alerted now and updated once GPS is found.")
    elif not resolved.gps_available:
        warnings.append("Live GPS unavailable; the last known location was shared.")

    # Step 4 - emergency contacts, highest priority first.
    contacts = list(user.contacts)
    if not contacts:
        warnings.append("No emergency contacts are configured, so nobody could be alerted.")

    # Step 8 (done before sending) - the incident is persisted first so it is never
    # lost, even if a notification channel misbehaves.
    incident = Incident(
        user=user,
        trigger=source,
        status=IncidentStatus.ACTIVE,
        gps_available=resolved.gps_available,
        location_source=resolved.source,
        risk_score=risk_score,
        note=note,
    )
    if resolved.coordinates is not None:
        incident.start_lat = resolved.coordinates.lat
        incident.start_lng = resolved.coordinates.lng
        incident.locations.append(_point(resolved.coordinates))
        if resolved.gps_available:
            remember_location(user, resolved.coordinates)
    db.session.add(incident)
    db.session.commit()

    # Steps 5-6 - compose and send.
    message = alert_service.build_emergency_message(user, incident)
    alerts = alert_service.dispatch(incident, contacts, message)

    # Step 7 - the incident is ACTIVE with a live share token: further location
    # updates extend the track that contacts see. Step 9 is `end_incident`.
    log.warning("Incident %s started for user %s via %s (%d alerts)", incident.id, user.id, source, len(alerts))
    return TriggerResult(incident, created=True, alerts=alerts, warnings=warnings)


def add_location(incident: Incident, user: User, coords: Coordinates) -> LocationPoint:
    """Live location tracking while the emergency is active."""
    if not incident.is_active:
        raise Conflict("This emergency has already ended.", code="incident_not_active")
    point = _append_location(incident, user, coords)
    db.session.commit()
    return point


def end_incident(incident: Incident, user: User, reason: str) -> list[Alert]:
    """Step 9: the user cancels emergency mode. Contacts get an all-clear message."""
    if not incident.is_active:
        raise Conflict("This emergency has already ended.", code="incident_not_active")
    incident.status = IncidentStatus.FALSE_ALARM if reason == "false_alarm" else IncidentStatus.RESOLVED
    incident.end_reason = reason
    incident.ended_at = utcnow()
    db.session.commit()
    log.warning("Incident %s ended by user %s (%s)", incident.id, user.id, reason)

    # Only people who were told about the emergency need the all-clear.
    alerted_ids = {alert.contact_id for alert in incident.alerts}
    contacts = [contact for contact in user.contacts if contact.id in alerted_ids]
    return alert_service.dispatch(incident, contacts, alert_service.build_all_clear_message(user, incident))


def _append_location(incident: Incident, user: User, coords: Coordinates) -> LocationPoint:
    point = _point(coords)
    incident.locations.append(point)
    remember_location(user, coords)
    if incident.start_lat is None:
        # The first fix after an alert that went out without a location: tell contacts.
        incident.start_lat, incident.start_lng = coords.lat, coords.lng
        incident.gps_available = True
        incident.location_source = LocationSource.GPS
        db.session.commit()
        alerted_ids = {alert.contact_id for alert in incident.alerts}
        contacts = [contact for contact in user.contacts if contact.id in alerted_ids]
        alert_service.dispatch(incident, contacts, alert_service.build_location_update_message(user, incident))
    return point


def _point(coords: Coordinates) -> LocationPoint:
    return LocationPoint(lat=coords.lat, lng=coords.lng, accuracy_m=coords.accuracy_m, recorded_at=utcnow())
