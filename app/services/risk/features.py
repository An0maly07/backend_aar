"""Feature engineering for the AI risk model.

Signals come from the blueprint's "AI-Based Threat Detection" list: sudden
acceleration, sudden fall, abnormal movement, heart-rate change, voice distress
and location/time pattern (night time).
"""
from datetime import datetime

FEATURE_NAMES = [
    "accel_peak_g",       # peak acceleration magnitude in g (1.0 = at rest)
    "fall_detected",      # 1 if the device's free-fall/impact detector fired
    "movement_variance",  # variance of acceleration over the window (abnormal movement)
    "heart_rate",         # beats per minute
    "heart_rate_delta",   # heart rate minus the user's resting baseline
    "voice_distress",     # 0..1 distress probability from on-device audio analysis
    "is_night",           # 1 between 21:00 and 05:59 local time
]

NIGHT_HOURS = {21, 22, 23, 0, 1, 2, 3, 4, 5}


def build_features(reading: dict, baseline_heart_rate: int) -> dict[str, float]:
    heart_rate = reading.get("heart_rate")
    if heart_rate is None:
        heart_rate = baseline_heart_rate  # no wearable: treat as resting
    local_hour = reading.get("local_hour")
    if local_hour is None:
        local_hour = datetime.now().hour

    return {
        "accel_peak_g": float(reading.get("accel_peak_g", 1.0)),
        "fall_detected": 1.0 if reading.get("fall_detected") else 0.0,
        "movement_variance": float(reading.get("movement_variance", 0.0)),
        "heart_rate": float(heart_rate),
        "heart_rate_delta": float(heart_rate - baseline_heart_rate),
        "voice_distress": float(reading.get("voice_distress", 0.0)),
        "is_night": 1.0 if local_hour in NIGHT_HOURS else 0.0,
    }


def to_vector(features: dict[str, float], names: list[str] | None = None) -> list[float]:
    return [features[name] for name in (names or FEATURE_NAMES)]
