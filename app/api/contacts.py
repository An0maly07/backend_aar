"""Emergency contacts (trusted friends and family)."""
from flask import Blueprint, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.api import get_owned_or_404, load_json
from app.errors import Conflict, Unprocessable
from app.extensions import db
from app.models import EmergencyContact
from app.schemas import ContactSchema

bp = Blueprint("contacts", __name__, url_prefix="/api/contacts")


def _check_reachable(phone: str | None, email: str | None) -> None:
    if not phone and not email:
        raise Unprocessable("A contact needs a phone number or an email address.",
                            details={"phone": ["Provide phone or email."]})


def _commit_or_conflict() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict("You already have a contact with this phone number.", code="duplicate_contact")


@bp.get("")
@login_required
def list_contacts():
    return {"contacts": [contact.to_dict() for contact in current_user.contacts]}


@bp.post("")
@login_required
def create_contact():
    data = load_json(ContactSchema())
    _check_reachable(data.get("phone"), data.get("email"))
    contacts = current_user.contacts
    if len(contacts) >= current_app.config["MAX_CONTACTS"]:
        raise Conflict(f"You can have at most {current_app.config['MAX_CONTACTS']} emergency contacts.",
                       code="contact_limit")
    if "priority" not in data:
        data["priority"] = max((c.priority for c in contacts), default=0) + 1
    contact = EmergencyContact(user_id=current_user.id, **data)
    db.session.add(contact)
    _commit_or_conflict()
    return {"contact": contact.to_dict()}, 201


@bp.get("/<int:contact_id>")
@login_required
def get_contact(contact_id: int):
    return {"contact": get_owned_or_404(EmergencyContact, contact_id, "Contact not found.").to_dict()}


@bp.patch("/<int:contact_id>")
@login_required
def update_contact(contact_id: int):
    contact = get_owned_or_404(EmergencyContact, contact_id, "Contact not found.")
    data = load_json(ContactSchema(), partial=True)
    _check_reachable(data.get("phone", contact.phone), data.get("email", contact.email))
    for key, value in data.items():
        setattr(contact, key, value)
    _commit_or_conflict()
    return {"contact": contact.to_dict()}


@bp.delete("/<int:contact_id>")
@login_required
def delete_contact(contact_id: int):
    contact = get_owned_or_404(EmergencyContact, contact_id, "Contact not found.")
    db.session.delete(contact)
    db.session.commit()
    return "", 204
