"""Voice Trigger -> Verify Command -> Emergency Engine."""
from flask import Blueprint, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.api import authenticated_user, get_owned_or_404, load_json
from app.api.sos import trigger_response
from app.errors import Conflict
from app.extensions import db, limiter
from app.models import IncidentTrigger, TriggerPhrase
from app.schemas import TriggerPhraseSchema, VoiceVerifySchema
from app.services import emergency_engine
from app.services.location_service import Coordinates
from app.services.voice_service import match_transcript, normalize

bp = Blueprint("voice", __name__, url_prefix="/api/voice")

MAX_PHRASES = 10


@bp.get("/phrases")
@login_required
def list_phrases():
    return {"phrases": [p.to_dict() for p in current_user.trigger_phrases]}


@bp.post("/phrases")
@login_required
def add_phrase():
    phrase = load_json(TriggerPhraseSchema())["phrase"]
    existing = current_user.trigger_phrases
    if len(existing) >= MAX_PHRASES:
        raise Conflict(f"You can have at most {MAX_PHRASES} trigger phrases.", code="phrase_limit")
    if any(normalize(p.phrase) == normalize(phrase) for p in existing):
        raise Conflict("You already have this trigger phrase.", code="duplicate_phrase")
    record = TriggerPhrase(user_id=current_user.id, phrase=phrase)
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict("You already have this trigger phrase.", code="duplicate_phrase")
    return {"phrase": record.to_dict()}, 201


@bp.delete("/phrases/<int:phrase_id>")
@login_required
def delete_phrase(phrase_id: int):
    db.session.delete(get_owned_or_404(TriggerPhrase, phrase_id, "Trigger phrase not found."))
    db.session.commit()
    return "", 204


@bp.post("/verify")
@login_required
@limiter.limit(lambda: current_app.config["SENSOR_RATE_LIMIT"])
def verify():
    data = load_json(VoiceVerifySchema())
    cfg = current_app.config
    user = authenticated_user()

    confidence = data.get("confidence")
    if confidence is not None and confidence < cfg["VOICE_MIN_CONFIDENCE"]:
        return {"verified": False, "reason": "low_confidence", "score": 0.0, "matched_phrase": None}

    phrases = [p.phrase for p in user.trigger_phrases]
    match = match_transcript(data["transcript"], phrases, cfg["VOICE_MATCH_THRESHOLD"])
    if not match.matched:
        return {"verified": False, "reason": "no_match", "score": match.score, "matched_phrase": None}

    result = emergency_engine.trigger(
        user, IncidentTrigger.VOICE, Coordinates.from_payload(data),
        note=f'Voice command matched "{match.phrase}"',
    )
    body, status = trigger_response(result)
    body.update({"verified": True, "reason": "matched", "score": match.score, "matched_phrase": match.phrase})
    return body, status
