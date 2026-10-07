from datetime import timedelta

import pytest

from app.extensions import db
from app.models import RiskAssessment
from app.services.risk.assessment import sweep_expired_assessments
from app.services.risk.features import build_features
from app.services.risk.policy import decide
from app.services.risk.scorer import RiskScorer, rule_based_score
from app.services.risk.train import train_and_save
from app.utils.time import utcnow
from tests.conftest import PUNE, add_contact

CALM = {"accel_peak_g": 1.1, "movement_variance": 0.4, "heart_rate": 80, "voice_distress": 0.05, "local_hour": 14}
FALL = {"accel_peak_g": 4.6, "fall_detected": True, "movement_variance": 0.3, "heart_rate": 105,
        "voice_distress": 0.3, "local_hour": 14}
STRUGGLE = {"accel_peak_g": 3.6, "movement_variance": 3.8, "heart_rate": 140, "voice_distress": 0.7,
            "local_hour": 23}


class FixedScorer:
    source = "stub"

    def __init__(self, score):
        self.value = score

    def score(self, features):
        return self.value

    def info(self):
        return {"scorer": "stub"}


@pytest.fixture
def fixed_score(app):
    def _set(value):
        app.extensions["risk_scorer"] = FixedScorer(value)
    return _set


@pytest.mark.parametrize("score, expected", [
    (0.0, ("low", "no_action")),
    (0.39, ("low", "no_action")),
    (0.40, ("medium", "ask_user")),
    (0.74, ("medium", "ask_user")),
    (0.75, ("high", "emergency_alert")),
])
def test_policy_matches_blueprint(score, expected):
    assert decide(score, 0.40, 0.75) == expected


def test_rule_based_scores_are_ordered():
    calm = rule_based_score(build_features(CALM, 75))
    fall = rule_based_score(build_features(FALL, 75))
    struggle = rule_based_score(build_features(STRUGGLE, 75))
    assert calm < 0.40 <= fall < 0.75 <= struggle


def test_trained_model_maps_scenarios_to_blueprint_levels(tmp_path):
    path = tmp_path / "risk.joblib"
    meta = train_and_save(path, n_samples=6000, seed=7)
    assert meta["metrics"]["roc_auc"] > 0.85
    assert path.with_suffix(".json").exists()

    scorer = RiskScorer.load(path)
    assert scorer.source == "model"
    level = {name: decide(scorer.score(build_features(reading, 75)), 0.40, 0.75)[0]
             for name, reading in {"calm": CALM, "fall": FALL, "struggle": STRUGGLE}.items()}
    assert level == {"calm": "low", "fall": "medium", "struggle": "high"}


def test_missing_model_falls_back_to_rules(tmp_path):
    assert RiskScorer.load(tmp_path / "nope.joblib").source == "rules"


def test_low_risk_takes_no_action(client, user):
    body = client.post("/api/ai/assess", json=CALM).get_json()
    assert body["assessment"]["level"] == "low"
    assert body["assessment"]["status"] == "no_action"
    assert body["incident"] is None


def test_high_risk_raises_emergency_immediately(client, user, outbox):
    add_contact(client)
    response = client.post("/api/ai/assess", json={**STRUGGLE, **PUNE})
    assert response.status_code == 201
    body = response.get_json()
    assert body["assessment"]["action"] == "emergency_alert"
    assert body["assessment"]["status"] == "escalated"
    assert body["incident"]["trigger"] == "ai"
    assert body["incident"]["risk_score"] >= 0.75
    assert "automatic risk detection" in outbox[-1]["body"]


def test_medium_risk_asks_user_who_confirms_safe(client, user, fixed_score):
    fixed_score(0.5)
    body = client.post("/api/ai/assess", json=FALL).get_json()
    assessment = body["assessment"]
    assert assessment["status"] == "awaiting_user" and assessment["expires_at"]

    # Streaming readings don't stack up more questions.
    again = client.post("/api/ai/assess", json=FALL).get_json()["assessment"]
    assert again["id"] == assessment["id"]
    assert client.get("/api/dashboard").get_json()["pending_risk_check"]["id"] == assessment["id"]

    safe = client.post(f"/api/ai/assessments/{assessment['id']}/respond", json={"safe": True})
    assert safe.status_code == 200
    assert safe.get_json()["assessment"]["status"] == "confirmed_safe"
    assert client.post(f"/api/ai/assessments/{assessment['id']}/respond", json={"safe": False}).status_code == 409
    assert client.get("/api/sos/active").get_json()["incident"] is None


def test_medium_risk_user_says_not_safe(client, user, fixed_score):
    add_contact(client)
    fixed_score(0.6)
    assessment = client.post("/api/ai/assess", json={**FALL, **PUNE}).get_json()["assessment"]
    response = client.post(f"/api/ai/assessments/{assessment['id']}/respond", json={"safe": False})
    assert response.status_code == 201
    assert response.get_json()["incident"]["trigger"] == "ai"
    assert response.get_json()["assessment"]["status"] == "escalated"


def test_unanswered_medium_risk_escalates_after_window(app, client, user, fixed_score):
    add_contact(client)
    fixed_score(0.6)
    assessment_id = client.post("/api/ai/assess", json={**FALL, **PUNE}).get_json()["assessment"]["id"]

    with app.app_context():
        assert sweep_expired_assessments() == 0  # still inside the window
        record = db.session.get(RiskAssessment, assessment_id)
        record.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        assert sweep_expired_assessments() == 1
    incident = client.get("/api/sos/active").get_json()["incident"]
    assert incident["trigger"] == "ai"
    assert incident["note"] == "Automatic: no response to risk check"

    late = client.post(f"/api/ai/assessments/{assessment_id}/respond", json={"safe": True})
    assert late.status_code == 409
    assert late.get_json()["error"]["details"]["incident_id"] == incident["id"]


def test_assessments_are_private(client, user, other_client, fixed_score):
    fixed_score(0.5)
    assessment_id = client.post("/api/ai/assess", json=FALL).get_json()["assessment"]["id"]
    response = other_client.post(f"/api/ai/assessments/{assessment_id}/respond", json={"safe": True})
    assert response.status_code == 404


def test_model_info(client, user):
    info = client.get("/api/ai/model-info").get_json()
    assert info["scorer"] == "rules"
    assert "ask user" in info["policy"]["medium"]
