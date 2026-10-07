"""Risk score -> action, exactly as in the blueprint:

    Low    -> No Action
    Medium -> Ask User
    High   -> Emergency Alert
"""
from app.models import RiskAction, RiskLevel


def decide(score: float, medium_threshold: float, high_threshold: float) -> tuple[str, str]:
    if score >= high_threshold:
        return RiskLevel.HIGH, RiskAction.EMERGENCY_ALERT
    if score >= medium_threshold:
        return RiskLevel.MEDIUM, RiskAction.ASK_USER
    return RiskLevel.LOW, RiskAction.NO_ACTION
