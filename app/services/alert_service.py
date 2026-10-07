"""Alert system: compose emergency messages and fan them out to contacts.

Every (contact, channel) pair becomes one ``Alert`` row, so delivery is fully
auditable and one failing channel never blocks the others.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, current_app

from app.extensions import db
from app.models import Alert, AlertKind, AlertStatus, EmergencyContact, Incident, User
from app.services.location_service import google_maps_link, osm_link
from app.services.notifiers import NotifierError, OutgoingMessage, enabled_notifiers, get_notifier
from app.utils.time import utcnow

log = logging.getLogger(__name__)

_TRIGGER_LABELS = {
    "sos": "pressed the SOS button",
    "voice": "used a voice emergency command",
    "ai": "was flagged in danger by automatic risk detection",
}

_executor: ThreadPoolExecutor | None = None


def _location_lines(incident: Incident) -> list[str]:
    point = incident.latest_location
    if point is None:
        return ["Location: not available yet - you will get an update once GPS is found."]
    lines = [
        f"Location: {google_maps_link(point.lat, point.lng)}",
        f"OpenStreetMap: {osm_link(point.lat, point.lng)}",
    ]
    if not incident.gps_available:
        lines.append("(Last known location - live GPS was unavailable when the alert was raised.)")
    return lines


def build_emergency_message(user: User, incident: Incident) -> OutgoingMessage:
    """Algorithm step 5: create the emergency message."""
    action = _TRIGGER_LABELS.get(incident.trigger, "raised an emergency")
    lines = [
        f"EMERGENCY ALERT: {user.name} {action} at {incident.started_at:%d %b %Y %H:%M} UTC and may need help.",
        *_location_lines(incident),
        f"Live tracking: {incident.tracking_url}",
    ]
    if user.custom_message:
        lines.append(f'Message from {user.first_name}: "{user.custom_message}"')
    lines.append(
        f"Please call {user.first_name} at {user.phone}. "
        f"If you cannot reach them, call emergency services ({current_app.config['EMERGENCY_NUMBER']})."
    )
    return OutgoingMessage(AlertKind.EMERGENCY, f"EMERGENCY: {user.name} needs help", "\n".join(lines))


def build_location_update_message(user: User, incident: Incident) -> OutgoingMessage:
    lines = [
        f"UPDATE: {user.name}'s location is now available.",
        *_location_lines(incident),
        f"Live tracking: {incident.tracking_url}",
    ]
    return OutgoingMessage(AlertKind.UPDATE, f"UPDATE: {user.name}'s location", "\n".join(lines))


def build_all_clear_message(user: User, incident: Incident) -> OutgoingMessage:
    body = (
        f"ALL CLEAR: {user.name} has marked themselves safe and ended the emergency "
        f"(reason: {incident.end_reason.replace('_', ' ')}). Thank you for responding."
    )
    return OutgoingMessage(AlertKind.ALL_CLEAR, f"ALL CLEAR: {user.name} is safe", body)


def dispatch(incident: Incident, contacts: list[EmergencyContact], message: OutgoingMessage) -> list[Alert]:
    """Algorithm step 6: send the alert to every contact on every enabled channel."""
    alerts: list[Alert] = []
    for contact in contacts:
        for notifier in enabled_notifiers():
            recipient = notifier.address_for(contact)
            if not recipient:
                continue
            alert = Alert(
                incident=incident,
                contact_id=contact.id,
                contact_name=contact.name,
                channel=notifier.channel,
                recipient=recipient,
                kind=message.kind,
                status=AlertStatus.QUEUED,
            )
            db.session.add(alert)
            alerts.append(alert)
    db.session.commit()

    if not alerts:
        return alerts
    if current_app.config["ALERT_ASYNC"]:
        app = current_app._get_current_object()
        _get_executor().submit(_deliver_in_background, app, [a.id for a in alerts], message)
    else:
        _deliver(alerts, message)
        db.session.commit()
    return alerts


def _deliver(alerts: list[Alert], message: OutgoingMessage) -> None:
    for alert in alerts:
        try:
            get_notifier(alert.channel).send(alert.recipient, message)
        except NotifierError as exc:
            alert.status = AlertStatus.FAILED
            alert.error = str(exc)[:500]
            log.error("Alert %s via %s failed: %s", alert.id, alert.channel, exc)
        except Exception as exc:  # never let one broken channel abort the fan-out
            alert.status = AlertStatus.FAILED
            alert.error = f"Unexpected error: {exc}"[:500]
            log.exception("Alert %s via %s crashed", alert.id, alert.channel)
        else:
            alert.status = AlertStatus.SENT
            alert.sent_at = utcnow()
            log.info("Alert %s (%s) sent via %s to contact %s", alert.id, alert.kind, alert.channel, alert.contact_id)


def _deliver_in_background(app: Flask, alert_ids: list[int], message: OutgoingMessage) -> None:
    with app.app_context():
        try:
            alerts = db.session.scalars(db.select(Alert).where(Alert.id.in_(alert_ids))).all()
            _deliver(list(alerts), message)
            db.session.commit()
        except Exception:
            log.exception("Background alert delivery failed")
            db.session.rollback()
        finally:
            db.session.remove()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alerts")
    return _executor
