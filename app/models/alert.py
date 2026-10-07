from app.extensions import db
from app.utils.time import isoformat, utcnow


class AlertKind:
    EMERGENCY = "emergency"
    UPDATE = "update"  # e.g. GPS fix arrived after an alert was sent without a location
    ALL_CLEAR = "all_clear"


class AlertStatus:
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class Alert(db.Model):
    """One message to one contact over one channel (the "Alert system" audit trail)."""

    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    # Kept nullable so history survives if the contact is later deleted.
    contact_id = db.Column(db.Integer, db.ForeignKey("emergency_contacts.id", ondelete="SET NULL"), index=True)
    contact_name = db.Column(db.String(120), nullable=False)
    channel = db.Column(db.String(16), nullable=False)
    recipient = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default=AlertKind.EMERGENCY)
    status = db.Column(db.String(16), nullable=False, default=AlertStatus.QUEUED)
    error = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sent_at = db.Column(db.DateTime)

    incident = db.relationship("Incident", back_populates="alerts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "contact_name": self.contact_name,
            "channel": self.channel,
            "recipient": self.recipient,
            "kind": self.kind,
            "status": self.status,
            "error": self.error,
            "created_at": isoformat(self.created_at),
            "sent_at": isoformat(self.sent_at),
        }
