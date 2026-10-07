"""Application configuration.

Everything is read from environment variables (optionally loaded from a ``.env``
file). Switching from SQLite to MySQL, as planned in the project blueprint, is
only a matter of changing ``DATABASE_URL``.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")

    # --- Database -----------------------------------------------------------
    # SQLite for the prototype; MySQL later, e.g.
    # mysql+pymysql://user:password@localhost:3306/women_safety?charset=utf8mb4
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'instance' / 'women_safety.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Sessions (password hashing + secure sessions) -----------------------
    SESSION_COOKIE_NAME = "ws_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)

    # --- CORS / frontend ----------------------------------------------------
    FRONTEND_ORIGINS = _list("FRONTEND_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    # Used to build the live-tracking link that is sent to emergency contacts.
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")

    # --- Rate limiting --------------------------------------------------------
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    AUTH_RATE_LIMIT = os.getenv("AUTH_RATE_LIMIT", "10 per minute")
    SENSOR_RATE_LIMIT = os.getenv("SENSOR_RATE_LIMIT", "120 per minute")
    TRACKING_RATE_LIMIT = os.getenv("TRACKING_RATE_LIMIT", "120 per minute")

    # --- Alert system ---------------------------------------------------------
    # Comma-separated list of: console, email, sms
    ALERT_CHANNELS = _list("ALERT_CHANNELS", "console")
    ALERT_ASYNC = _bool("ALERT_ASYNC", False)
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
    SMTP_FROM = os.getenv("SMTP_FROM", "alerts@women-safety.local")
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

    # --- Domain rules ---------------------------------------------------------
    MAX_CONTACTS = int(os.getenv("MAX_CONTACTS", "10"))
    LOCATION_STALE_MINUTES = int(os.getenv("LOCATION_STALE_MINUTES", "15"))
    DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "+91")
    EMERGENCY_NUMBER = os.getenv("EMERGENCY_NUMBER", "112")

    # --- Voice trigger --------------------------------------------------------
    DEFAULT_TRIGGER_PHRASES = _list("DEFAULT_TRIGGER_PHRASES", "help me,bachao,emergency")
    VOICE_MATCH_THRESHOLD = float(os.getenv("VOICE_MATCH_THRESHOLD", "0.8"))
    VOICE_MIN_CONFIDENCE = float(os.getenv("VOICE_MIN_CONFIDENCE", "0.5"))

    # --- AI risk detection ----------------------------------------------------
    RISK_MODEL_PATH = os.getenv("RISK_MODEL_PATH", str(BASE_DIR / "ml" / "risk_model.joblib"))
    RISK_MEDIUM_THRESHOLD = float(os.getenv("RISK_MEDIUM_THRESHOLD", "0.40"))
    RISK_HIGH_THRESHOLD = float(os.getenv("RISK_HIGH_THRESHOLD", "0.75"))
    RISK_CONFIRM_WINDOW_SECONDS = int(os.getenv("RISK_CONFIRM_WINDOW_SECONDS", "60"))
    BASELINE_HEART_RATE = int(os.getenv("BASELINE_HEART_RATE", "75"))

    # Background sweeper that escalates unanswered "Medium -> ask user" checks.
    ENABLE_SWEEPER = _bool("ENABLE_SWEEPER", True)
    SWEEPER_INTERVAL_SECONDS = int(os.getenv("SWEEPER_INTERVAL_SECONDS", "10"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    ALERT_CHANNELS = ["console"]
    ALERT_ASYNC = False
    ENABLE_SWEEPER = False
    PUBLIC_BASE_URL = "http://testserver"
    RISK_MODEL_PATH = str(BASE_DIR / "ml" / "__missing_in_tests__.joblib")


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
