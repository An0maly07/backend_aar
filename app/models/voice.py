from app.extensions import db
from app.utils.time import isoformat, utcnow


class TriggerPhrase(db.Model):
    """A phrase that, when spoken, triggers an emergency ("Voice Trigger")."""

    __tablename__ = "trigger_phrases"
    __table_args__ = (db.UniqueConstraint("user_id", "phrase", name="uq_trigger_phrases_user_phrase"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    phrase = db.Column(db.String(60), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="trigger_phrases")

    def to_dict(self) -> dict:
        return {"id": self.id, "phrase": self.phrase, "created_at": isoformat(self.created_at)}
