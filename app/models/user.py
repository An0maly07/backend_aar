from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.utils.time import isoformat, utcnow


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(20), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Optional personal note appended to every emergency alert.
    custom_message = db.Column(db.String(280))
    # Resting heart rate, used by the AI risk model to compute heart-rate change.
    baseline_heart_rate = db.Column(db.Integer)

    # Only the *latest* location outside an incident is kept (privacy by design);
    # it is the fallback when GPS is unavailable at SOS time.
    last_lat = db.Column(db.Float)
    last_lng = db.Column(db.Float)
    last_accuracy_m = db.Column(db.Float)
    last_location_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    contacts = db.relationship(
        "EmergencyContact",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="(EmergencyContact.priority, EmergencyContact.id)",
    )
    trigger_phrases = db.relationship(
        "TriggerPhrase", back_populates="user", cascade="all, delete-orphan", order_by="TriggerPhrase.id"
    )
    incidents = db.relationship("Incident", back_populates="user", cascade="all, delete-orphan")
    risk_assessments = db.relationship("RiskAssessment", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name else ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "custom_message": self.custom_message,
            "baseline_heart_rate": self.baseline_heart_rate,
            "last_location": self.last_location_dict(),
            "created_at": isoformat(self.created_at),
        }

    def last_location_dict(self) -> dict | None:
        if self.last_lat is None or self.last_lng is None:
            return None
        return {
            "lat": self.last_lat,
            "lng": self.last_lng,
            "accuracy_m": self.last_accuracy_m,
            "recorded_at": isoformat(self.last_location_at),
        }
