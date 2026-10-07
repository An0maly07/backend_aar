from app.extensions import db
from app.utils.time import isoformat, utcnow


class LocationPoint(db.Model):
    """A point on an incident's live track."""

    __tablename__ = "location_points"
    __table_args__ = (db.Index("ix_location_points_incident_time", "incident_id", "recorded_at"),)

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    accuracy_m = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    incident = db.relationship("Incident", back_populates="locations")

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "accuracy_m": self.accuracy_m,
            "recorded_at": isoformat(self.recorded_at),
        }
