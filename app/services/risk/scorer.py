"""Risk scoring: the trained scikit-learn model, with a rule-based fallback.

The fallback keeps "AI Detection" working (and explainable) even before
``flask train-risk-model`` has been run.
"""
import logging
import math
from pathlib import Path

import joblib

from app.services.risk.features import FEATURE_NAMES, to_vector

log = logging.getLogger(__name__)


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def rule_based_score(f: dict[str, float]) -> float:
    """Hand-tuned logistic score over normalised signals (0 = calm, 1 = danger)."""
    z = (
        -4.0
        + 2.0 * _clip((f["accel_peak_g"] - 2.0) / 3.0)
        + 1.5 * f["fall_detected"]
        + 1.5 * _clip((f["movement_variance"] - 1.0) / 3.0)
        + 1.5 * _clip((f["heart_rate_delta"] - 20.0) / 50.0)
        + 3.5 * _clip((f["voice_distress"] - 0.2) / 0.6)
        + 0.8 * f["is_night"]
    )
    return 1.0 / (1.0 + math.exp(-z))


class RiskScorer:
    def __init__(self, bundle: dict | None = None):
        self.bundle = bundle

    @classmethod
    def load(cls, path: str | Path) -> "RiskScorer":
        path = Path(path)
        if not path.exists():
            log.info("No risk model at %s; using rule-based scoring.", path)
            return cls()
        try:
            # joblib uses pickle: only ever load a model file this project produced.
            bundle = joblib.load(path)
            log.info("Loaded risk model %s from %s", bundle.get("version"), path)
            return cls(bundle)
        except Exception:
            log.exception("Could not load risk model from %s; using rule-based scoring.", path)
            return cls()

    @property
    def source(self) -> str:
        return "model" if self.bundle else "rules"

    def score(self, features: dict[str, float]) -> float:
        if not self.bundle:
            return rule_based_score(features)
        names = self.bundle.get("feature_names", FEATURE_NAMES)
        probability = self.bundle["model"].predict_proba([to_vector(features, names)])[0][1]
        return float(probability)

    def info(self) -> dict:
        if not self.bundle:
            return {"scorer": "rules", "feature_names": FEATURE_NAMES}
        return {
            "scorer": "model",
            "version": self.bundle.get("version"),
            "algorithm": type(self.bundle["model"]).__name__,
            "trained_at": self.bundle.get("trained_at"),
            "feature_names": self.bundle.get("feature_names"),
            "metrics": self.bundle.get("metrics"),
            "training_data": self.bundle.get("training_data"),
        }
