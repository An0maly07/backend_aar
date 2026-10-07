"""Authentication: register, login, logout (password hashing + secure sessions)."""
from flask import Blueprint, current_app, session
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.api import load_json
from app.errors import Conflict, Unauthorized
from app.extensions import db, limiter
from app.models import TriggerPhrase, User
from app.schemas import LoginSchema, RegisterSchema
from app.services.emergency_engine import get_active_incident

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_auth_limit = limiter.limit(lambda: current_app.config["AUTH_RATE_LIMIT"])
_dummy_hash: str | None = None


def _equalise_timing(password: str) -> None:
    """Hash anyway for unknown accounts so response time doesn't reveal which emails exist."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = generate_password_hash("not-a-real-password")
    check_password_hash(_dummy_hash, password)


@bp.post("/register")
@_auth_limit
def register():
    data = load_json(RegisterSchema())
    if db.session.scalar(db.select(User.id).where(User.email == data["email"])):
        raise Conflict("An account with this email already exists.", code="email_taken")
    if db.session.scalar(db.select(User.id).where(User.phone == data["phone"])):
        raise Conflict("An account with this phone number already exists.", code="phone_taken")

    user = User(name=data["name"], email=data["email"], phone=data["phone"])
    user.set_password(data["password"])
    user.trigger_phrases = [TriggerPhrase(phrase=p) for p in current_app.config["DEFAULT_TRIGGER_PHRASES"]]
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict("An account with these details already exists.", code="account_exists")

    session.clear()
    login_user(user)
    return {"user": user.to_dict()}, 201


@bp.post("/login")
@_auth_limit
def login():
    data = load_json(LoginSchema())
    column, value = (User.email, data["email"]) if data.get("email") else (User.phone, data["phone"])
    user = db.session.scalars(db.select(User).where(column == value)).first()
    if user is None:
        _equalise_timing(data["password"])
        raise Unauthorized("Invalid credentials.", code="invalid_credentials")
    if not user.check_password(data["password"]):
        raise Unauthorized("Invalid credentials.", code="invalid_credentials")

    session.clear()  # fresh session on login (prevents session fixation)
    login_user(user, remember=data["remember"])
    return {"user": user.to_dict()}


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return {"message": "Logged out."}


@bp.get("/me")
@login_required
def me():
    active = get_active_incident(current_user)
    return {
        "user": current_user.to_dict(),
        "active_incident": active.to_dict() if active else None,
    }
