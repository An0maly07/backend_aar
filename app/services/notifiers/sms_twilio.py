from flask import current_app

from app.models import EmergencyContact
from app.services.notifiers.base import Notifier, NotifierError, OutgoingMessage


class TwilioSmsNotifier(Notifier):
    """SMS alerts through Twilio. Requires ``pip install twilio`` and credentials."""

    channel = "sms"

    def address_for(self, contact: EmergencyContact) -> str | None:
        return contact.phone if contact.phone and contact.notify_sms else None

    def send(self, recipient: str, message: OutgoingMessage) -> None:
        cfg = current_app.config
        if not (cfg["TWILIO_ACCOUNT_SID"] and cfg["TWILIO_AUTH_TOKEN"] and cfg["TWILIO_FROM_NUMBER"]):
            raise NotifierError("Twilio credentials are not configured.")
        try:
            from twilio.rest import Client  # optional dependency
        except ImportError as exc:
            raise NotifierError("The 'twilio' package is not installed.") from exc

        try:
            client = Client(cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"])
            client.messages.create(to=recipient, from_=cfg["TWILIO_FROM_NUMBER"], body=message.body)
        except Exception as exc:  # Twilio raises its own exception hierarchy
            raise NotifierError(f"SMS delivery failed: {exc}") from exc
