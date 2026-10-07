"""HTTP API. One blueprint per module of the project blueprint."""
from flask import Flask, request
from flask_login import current_user
from marshmallow import Schema

from app.errors import APIError, NotFound
from app.extensions import db


def authenticated_user():
    """The real ``User`` behind Flask-Login's proxy, safe to hand to services and the ORM."""
    return current_user._get_current_object()


def load_json(schema: Schema, *, partial: bool = False) -> dict:
    """Validate the JSON body with ``schema``; an empty body counts as ``{}``."""
    data = request.get_json(silent=True)
    if data is None:
        if request.get_data(cache=True):
            raise APIError("Request body is not valid JSON.", code="malformed_json")
        data = {}
    if not isinstance(data, dict):
        raise APIError("Request body must be a JSON object.", code="malformed_json")
    return schema.load(data, partial=partial)


def get_owned_or_404(model, object_id: int, message: str = "Not found."):
    """Fetch a row that belongs to the logged-in user. Other users' rows look like 404s."""
    obj = db.session.scalars(
        db.select(model).where(model.id == object_id, model.user_id == current_user.id)
    ).first()
    if obj is None:
        raise NotFound(message)
    return obj


def register_blueprints(app: Flask) -> None:
    from app.api import (ai, auth, contacts, dashboard, health, incidents, location, profile, sos, tracking,
                         voice)

    for module in (auth, profile, dashboard, contacts, sos, location, incidents, voice, ai, tracking, health):
        app.register_blueprint(module.bp)
