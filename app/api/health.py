from flask import Blueprint, current_app
from sqlalchemy import text

from app.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/")
def index():
    return {
        "service": "Women Safety System API",
        "health": "/api/health",
        "docs": "See README.md for the full API reference.",
    }


@bp.get("/api/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "risk_scorer": current_app.extensions["risk_scorer"].source,
        "alert_channels": current_app.config["ALERT_CHANNELS"],
    }, 200 if database == "ok" else 503
