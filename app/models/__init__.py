"""Database models. Importing this package registers every table with SQLAlchemy."""
from app.models.alert import Alert, AlertKind, AlertStatus
from app.models.contact import EmergencyContact
from app.models.incident import Incident, IncidentStatus, IncidentTrigger, LocationSource
from app.models.location import LocationPoint
from app.models.risk import AssessmentStatus, RiskAction, RiskAssessment, RiskLevel
from app.models.user import User
from app.models.voice import TriggerPhrase

__all__ = [
    "Alert",
    "AlertKind",
    "AlertStatus",
    "AssessmentStatus",
    "EmergencyContact",
    "Incident",
    "IncidentStatus",
    "IncidentTrigger",
    "LocationPoint",
    "LocationSource",
    "RiskAction",
    "RiskAssessment",
    "RiskLevel",
    "TriggerPhrase",
    "User",
]
