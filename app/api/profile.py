"""Profile screen: view/update personal details, change password."""
from flask import Blueprint
from flask_login import current_user, login_required

from app.api import load_json
from app.errors import Conflict, Unauthorized
from app.extensions import db
from app.models import User
from app.schemas import PasswordChangeSchema, ProfileUpdateSchema

bp = Blueprint("profile", __name__, url_prefix="/api/profile")


@bp.get("")
@login_required
def get_profile():
    return {"user": current_user.to_dict()}


@bp.patch("")
@login_required
def update_profile():
    data = load_json(ProfileUpdateSchema(), partial=True)
    for column, code in ((User.email, "email_taken"), (User.phone, "phone_taken")):
        value = data.get(column.key)
        if value and value != getattr(current_user, column.key):
            taken = db.session.scalar(db.select(User.id).where(column == value, User.id != current_user.id))
            if taken:
                raise Conflict(f"Another account already uses this {column.key}.", code=code)
    for key, value in data.items():
        setattr(current_user, key, value)
    db.session.commit()
    return {"user": current_user.to_dict()}


@bp.post("/password")
@login_required
def change_password():
    data = load_json(PasswordChangeSchema())
    if not current_user.check_password(data["current_password"]):
        raise Unauthorized("Current password is incorrect.", code="invalid_credentials")
    current_user.set_password(data["new_password"])
    db.session.commit()
    return {"message": "Password updated."}
