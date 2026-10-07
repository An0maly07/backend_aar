import logging

from flask import current_app

from app.models import EmergencyContact
from app.services.notifiers.base import Notifier, OutgoingMessage

log = logging.getLogger("alerts.console")


class ConsoleNotifier(Notifier):
    """Development channel: prints the alert and keeps it in an in-memory outbox.

    Needs no credentials, so the whole SOS flow can be demonstrated locally.
    """

    channel = "console"

    def address_for(self, contact: EmergencyContact) -> str | None:
        return contact.phone or contact.email

    def send(self, recipient: str, message: OutgoingMessage) -> None:
        current_app.extensions["alert_outbox"].append(
            {"channel": self.channel, "recipient": recipient, "kind": message.kind,
             "subject": message.subject, "body": message.body}
        )
        log.warning("\n----- [%s] to %s -----\n%s\n%s\n-----", message.kind.upper(), recipient,
                    message.subject, message.body)
