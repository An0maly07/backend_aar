import smtplib
from email.message import EmailMessage

from flask import current_app

from app.models import EmergencyContact
from app.services.notifiers.base import Notifier, NotifierError, OutgoingMessage


class EmailNotifier(Notifier):
    """Email alerts over SMTP (standard library only)."""

    channel = "email"

    def address_for(self, contact: EmergencyContact) -> str | None:
        return contact.email if contact.email and contact.notify_email else None

    def send(self, recipient: str, message: OutgoingMessage) -> None:
        cfg = current_app.config
        if not cfg["SMTP_HOST"]:
            raise NotifierError("SMTP_HOST is not configured.")

        email = EmailMessage()
        email["From"] = cfg["SMTP_FROM"]
        email["To"] = recipient
        email["Subject"] = message.subject
        email.set_content(message.body)

        try:
            with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=10) as smtp:
                if cfg["SMTP_USE_TLS"]:
                    smtp.starttls()
                if cfg["SMTP_USERNAME"]:
                    smtp.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
                smtp.send_message(email)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifierError(f"SMTP delivery failed: {exc}") from exc
