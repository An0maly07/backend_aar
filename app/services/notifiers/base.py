from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models import EmergencyContact


@dataclass(frozen=True)
class OutgoingMessage:
    kind: str
    subject: str
    body: str


class NotifierError(Exception):
    """Raised by a notifier when delivery fails; recorded on the Alert row."""


class Notifier(ABC):
    channel: str

    @abstractmethod
    def address_for(self, contact: EmergencyContact) -> str | None:
        """Where this channel would deliver to for ``contact``, or ``None`` if it can't."""

    @abstractmethod
    def send(self, recipient: str, message: OutgoingMessage) -> None:
        """Deliver ``message`` or raise :class:`NotifierError`."""
