"""Train the AI risk model on a synthetic sensor dataset.

There is no public labelled dataset for this exact sensor mix yet, so we
simulate realistic everyday activity (safe) and danger scenarios. This is
good enough to prototype the pipeline end to end; it is **not** a validated
safety model. Replace ``generate_dataset`` with real wearable recordings
(ESP32 + accelerometer + heart-rate sensor) when they exist.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from app.services.risk.features import FEATURE_NAMES

# Each scenario has a *probability* of being a real emergency rather than a hard
# label. A fall, for example, is often harmless, so the model learns a mid-range
# score for it - which is exactly the blueprint's "Medium -> ask the user" case.
#
# name: (p_danger, weight, accel(mean, sd), p_fall, movement(mean, sd),
#        heart_rate(mean, sd), voice_distress(mean, sd), p_night)
SCENARIOS = {
    "resting":         (0.01, 0.20, (1.0, 0.05), 0.00, (0.1, 0.05), (72, 6), (0.03, 0.03), 0.30),
    "walking":         (0.02, 0.20, (1.3, 0.15), 0.00, (0.5, 0.20), (88, 8), (0.05, 0.04), 0.20),
    "running":         (0.03, 0.12, (2.6, 0.50), 0.01, (2.0, 0.50), (145, 15), (0.08, 0.06), 0.10),
    "phone_dropped":   (0.08, 0.10, (4.0, 1.00), 0.70, (0.4, 0.20), (80, 8), (0.05, 0.04), 0.25),
    "loud_place":      (0.10, 0.08, (1.3, 0.20), 0.00, (0.7, 0.30), (90, 10), (0.35, 0.15), 0.50),
    "fall":            (0.55, 0.10, (4.5, 1.00), 0.90, (0.3, 0.20), (108, 15), (0.30, 0.20), 0.35),
    "struggle":        (0.97, 0.12, (3.5, 0.80), 0.30, (3.5, 0.80), (135, 15), (0.65, 0.20), 0.50),
    "distress_scream": (0.92, 0.08, (1.6, 0.40), 0.05, (1.3, 0.50), (122, 15), (0.88, 0.08), 0.70),
}


def generate_dataset(n_samples: int = 6000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    names = list(SCENARIOS)
    weights = np.array([SCENARIOS[n][1] for n in names])
    picks = rng.choice(len(names), size=n_samples, p=weights / weights.sum())

    rows, labels = [], []
    for idx in picks:
        p_danger, _, accel, p_fall, movement, hr, voice, p_night = SCENARIOS[names[idx]]
        baseline = rng.normal(75, 8)
        heart_rate = max(40.0, rng.normal(*hr))
        rows.append([
            max(0.0, rng.normal(*accel)),
            float(rng.random() < p_fall),
            max(0.0, rng.normal(*movement)),
            heart_rate,
            heart_rate - baseline,
            float(np.clip(rng.normal(*voice), 0.0, 1.0)),
            float(rng.random() < p_night),
        ])
        labels.append(int(rng.random() < p_danger))
    return np.array(rows), np.array(labels)


def train_and_save(output_path: str | Path, n_samples: int = 6000, seed: int = 42) -> dict:
    X, y = generate_dataset(n_samples, seed)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)

    model = RandomForestClassifier(
        # Large leaves keep the predicted probabilities smooth (well calibrated) rather than 0/1.
        n_estimators=300, max_depth=8, min_samples_leaf=25, random_state=seed, n_jobs=-1
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    predicted = (proba >= 0.5).astype(int)
    metrics = {
        "accuracy": round(accuracy_score(y_test, predicted), 4),
        "precision": round(precision_score(y_test, predicted), 4),
        "recall": round(recall_score(y_test, predicted), 4),
        "f1": round(f1_score(y_test, predicted), 4),
        "roc_auc": round(roc_auc_score(y_test, proba), 4),
        "test_samples": int(len(y_test)),
    }
    trained_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "version": f"rf-synthetic-{trained_at[:10]}",
        "trained_at": trained_at,
        "metrics": metrics,
        "training_data": {"type": "synthetic", "samples": n_samples, "seed": seed, "scenarios": list(SCENARIOS)},
        "sklearn_version": sklearn.__version__,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output_path)
    meta = {key: value for key, value in bundle.items() if key != "model"}
    meta["feature_importances"] = dict(zip(FEATURE_NAMES, map(lambda v: round(float(v), 4), model.feature_importances_)))
    output_path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    return meta
