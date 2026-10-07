"""Alert delivery channels, selected with the ``ALERT_CHANNELS`` setting."""
from flask import current_app

from app.services.notifiers.base import Notifier, NotifierError, OutgoingMessage
from app.services.notifiers.console import ConsoleNotifier
from app.services.notifiers.email_smtp import EmailNotifier
from app.services.notifiers.sms_twilio import TwilioSmsNotifier

_REGISTRY: dict[str, type[Notifier]] = {
    ConsoleNotifier.channel: ConsoleNotifier,
    EmailNotifier.channel: EmailNotifier,
    TwilioSmsNotifier.channel: TwilioSmsNotifier,
}


def get_notifier(channel: str) -> Notifier:
    return _REGISTRY[channel]()


def enabled_notifiers() -> list[Notifier]:
    channels = current_app.config["ALERT_CHANNELS"]
    unknown = set(channels) - set(_REGISTRY)
    if unknown:
        raise RuntimeError(f"Unknown ALERT_CHANNELS: {', '.join(sorted(unknown))}")
    return [get_notifier(channel) for channel in channels]


__all__ = ["Notifier", "NotifierError", "OutgoingMessage", "enabled_notifiers", "get_notifier"]
