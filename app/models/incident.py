import secrets

from flask import current_app

from app.extensions import db
from app.utils.time import isoformat, utcnow


class IncidentTrigger:
    SOS = "sos"
    VOICE = "voice"
    AI = "ai"
    ALL = (SOS, VOICE, AI)


class IncidentStatus:
    ACTIVE = "active"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"
    ALL = (ACTIVE, RESOLVED, FALSE_ALARM)


class LocationSource:
    GPS = "gps"
    LAST_KNOWN = "last_known"
    NONE = "none"


def new_share_token() -> str:
    return secrets.token_urlsafe(32)


class Incident(db.Model):
    """One emergency, from trigger until the user cancels it ("Track Incident")."""

    __tablename__ = "incidents"
    __table_args__ = (db.Index("ix_incidents_user_status", "user_id", "status"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False, default=IncidentStatus.ACTIVE)
    gps_available = db.Column(db.Boolean, nullable=False, default=False)
    location_source = db.Column(db.String(16), nullable=False, default=LocationSource.NONE)
    start_lat = db.Column(db.Float)
    start_lng = db.Column(db.Float)
    risk_score = db.Column(db.Float)
    note = db.Column(db.String(280))
    # Unguessable token for the public live-tracking link sent to contacts.
    share_token = db.Column(db.String(64), nullable=False, unique=True, default=new_share_token)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime)
    end_reason = db.Column(db.String(32))

    user = db.relationship("User", back_populates="incidents")
    locations = db.relationship(
        "LocationPoint",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="LocationPoint.recorded_at",
        lazy="selectin",
    )
    alerts = db.relationship(
        "Alert", back_populates="incident", cascade="all, delete-orphan", order_by="Alert.id", lazy="selectin"
    )

    @property
    def is_active(self) -> bool:
        return self.status == IncidentStatus.ACTIVE

    @property
    def latest_location(self):
        return self.locations[-1] if self.locations else None

    @property
    def tracking_url(self) -> str:
        return f"{current_app.config['PUBLIC_BASE_URL']}/track/{self.share_token}"

    def to_dict(self, *, include_locations: bool = False, include_alerts: bool = False) -> dict:
        latest = self.latest_location
        data = {
            "id": self.id,
            "trigger": self.trigger,
            "status": self.status,
            "gps_available": self.gps_available,
            "location_source": self.location_source,
            "start_location": (
                {"lat": self.start_lat, "lng": self.start_lng} if self.start_lat is not None else None
            ),
            "latest_location": latest.to_dict() if latest else None,
            "risk_score": self.risk_score,
            "note": self.note,
            "tracking_url": self.tracking_url,
            "started_at": isoformat(self.started_at),
            "ended_at": isoformat(self.ended_at),
            "end_reason": self.end_reason,
            "alert_count": len(self.alerts),
        }
        if include_locations:
            data["locations"] = [point.to_dict() for point in self.locations]
        if include_alerts:
            data["alerts"] = [alert.to_dict() for alert in self.alerts]
        return data
