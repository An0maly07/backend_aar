from app.extensions import db
from app.utils.time import isoformat, utcnow


class EmergencyContact(db.Model):
    """A trusted person (friend, family member) who is alerted in an emergency."""

    __tablename__ = "emergency_contacts"
    __table_args__ = (db.UniqueConstraint("user_id", "phone", name="uq_emergency_contacts_user_phone"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    relation = db.Column(db.String(60))
    # Lower number = alerted first.
    priority = db.Column(db.Integer, nullable=False, default=1)
    notify_sms = db.Column(db.Boolean, nullable=False, default=True)
    notify_email = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="contacts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "relation": self.relation,
            "priority": self.priority,
            "notify_sms": self.notify_sms,
            "notify_email": self.notify_email,
            "created_at": isoformat(self.created_at),
        }
