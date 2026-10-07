from app.extensions import db
from app.utils.time import isoformat, utcnow


class RiskLevel:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskAction:
    NO_ACTION = "no_action"
    ASK_USER = "ask_user"
    EMERGENCY_ALERT = "emergency_alert"


class AssessmentStatus:
    NO_ACTION = "no_action"
    AWAITING_USER = "awaiting_user"
    CONFIRMED_SAFE = "confirmed_safe"
    # Transient claim state so the sweeper and the user's reply can't both act on one assessment.
    ESCALATING = "escalating"
    ESCALATED = "escalated"


class RiskAssessment(db.Model):
    """One run of "AI Detection -> Risk Analysis" over a batch of sensor readings."""

    __tablename__ = "risk_assessments"
    __table_args__ = (db.Index("ix_risk_assessments_status_expires", "status", "expires_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    features = db.Column(db.JSON, nullable=False)
    score = db.Column(db.Float, nullable=False)
    scorer = db.Column(db.String(16), nullable=False)  # "model" or "rules"
    level = db.Column(db.String(16), nullable=False)
    action = db.Column(db.String(24), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    accuracy_m = db.Column(db.Float)
    expires_at = db.Column(db.DateTime)
    incident_id = db.Column(db.Integer, db.ForeignKey("incidents.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="risk_assessments")
    incident = db.relationship("Incident")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "score": round(self.score, 4),
            "scorer": self.scorer,
            "level": self.level,
            "action": self.action,
            "status": self.status,
            "features": self.features,
            "expires_at": isoformat(self.expires_at),
            "incident_id": self.incident_id,
            "created_at": isoformat(self.created_at),
            "resolved_at": isoformat(self.resolved_at),
        }
