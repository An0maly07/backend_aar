"""Request validation (marshmallow). Responses are built by each model's ``to_dict``."""
from flask import current_app
from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

from app.utils.phone import normalize_phone


class TrimmedString(fields.String):
    def _deserialize(self, value, attr, data, **kwargs):
        return super()._deserialize(value, attr, data, **kwargs).strip()


class PhoneField(fields.String):
    def _deserialize(self, value, attr, data, **kwargs):
        raw = super()._deserialize(value, attr, data, **kwargs)
        try:
            return normalize_phone(raw, current_app.config["DEFAULT_COUNTRY_CODE"])
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class EmailField(fields.Email):
    def _deserialize(self, value, attr, data, **kwargs):
        return super()._deserialize(value.strip() if isinstance(value, str) else value, attr, data, **kwargs).lower()


class OptionalLocationMixin(Schema):
    """GPS may be unavailable, so coordinates are optional but must come as a pair."""

    lat = fields.Float(load_default=None, allow_none=True, validate=validate.Range(-90, 90))
    lng = fields.Float(load_default=None, allow_none=True, validate=validate.Range(-180, 180))
    accuracy_m = fields.Float(load_default=None, allow_none=True, validate=validate.Range(0, 100_000))

    @validates_schema
    def _lat_lng_pair(self, data, **kwargs):
        if (data.get("lat") is None) != (data.get("lng") is None):
            raise ValidationError("Send both lat and lng, or neither.", "lat")


class LocationSchema(Schema):
    lat = fields.Float(required=True, validate=validate.Range(-90, 90))
    lng = fields.Float(required=True, validate=validate.Range(-180, 180))
    accuracy_m = fields.Float(load_default=None, allow_none=True, validate=validate.Range(0, 100_000))


# --- Authentication -----------------------------------------------------------

class RegisterSchema(Schema):
    name = TrimmedString(required=True, validate=validate.Length(2, 120))
    email = EmailField(required=True)
    phone = PhoneField(required=True)
    password = fields.String(required=True, load_only=True, validate=validate.Length(8, 128))


class LoginSchema(Schema):
    email = EmailField(load_default=None)
    phone = PhoneField(load_default=None)
    password = fields.String(required=True, load_only=True, validate=validate.Length(1, 128))
    remember = fields.Boolean(load_default=False)

    @validates_schema
    def _one_identifier(self, data, **kwargs):
        if bool(data.get("email")) == bool(data.get("phone")):
            raise ValidationError("Log in with either email or phone.", "email")


# --- Profile ------------------------------------------------------------------

class ProfileUpdateSchema(Schema):
    name = TrimmedString(validate=validate.Length(2, 120))
    email = EmailField()
    phone = PhoneField()
    custom_message = TrimmedString(allow_none=True, validate=validate.Length(max=280))
    baseline_heart_rate = fields.Integer(allow_none=True, validate=validate.Range(40, 120))


class PasswordChangeSchema(Schema):
    current_password = fields.String(required=True, load_only=True)
    new_password = fields.String(required=True, load_only=True, validate=validate.Length(8, 128))


# --- Emergency contacts ---------------------------------------------------------

class ContactSchema(Schema):
    name = TrimmedString(required=True, validate=validate.Length(1, 120))
    phone = PhoneField(load_default=None, allow_none=True)
    email = EmailField(load_default=None, allow_none=True)
    relation = TrimmedString(load_default=None, allow_none=True, validate=validate.Length(max=60))
    priority = fields.Integer(validate=validate.Range(1, 100))
    notify_sms = fields.Boolean(load_default=True)
    notify_email = fields.Boolean(load_default=True)


# --- SOS ------------------------------------------------------------------------

class SosTriggerSchema(OptionalLocationMixin):
    note = TrimmedString(load_default=None, allow_none=True, validate=validate.Length(max=280))


class SosCancelSchema(Schema):
    reason = fields.String(load_default="safe", validate=validate.OneOf(["safe", "false_alarm"]))


# --- Voice ------------------------------------------------------------------------

class TriggerPhraseSchema(Schema):
    phrase = TrimmedString(required=True, validate=validate.Length(2, 60))


class VoiceVerifySchema(OptionalLocationMixin):
    transcript = fields.String(required=True, validate=validate.Length(1, 500))
    # Recogniser confidence (Web Speech API gives 0..1); optional.
    confidence = fields.Float(load_default=None, allow_none=True, validate=validate.Range(0, 1))


# --- AI risk detection -------------------------------------------------------------

class SensorReadingSchema(OptionalLocationMixin):
    """One window of sensor data from the phone or (later) the ESP32 wearable."""

    class Meta:
        unknown = EXCLUDE  # devices may send extra telemetry

    accel_peak_g = fields.Float(load_default=1.0, validate=validate.Range(0, 50))
    fall_detected = fields.Boolean(load_default=False)
    movement_variance = fields.Float(load_default=0.0, validate=validate.Range(0, 100))
    heart_rate = fields.Integer(load_default=None, allow_none=True, validate=validate.Range(25, 250))
    voice_distress = fields.Float(load_default=0.0, validate=validate.Range(0, 1))
    local_hour = fields.Integer(load_default=None, allow_none=True, validate=validate.Range(0, 23))


class RiskResponseSchema(Schema):
    safe = fields.Boolean(required=True)


class PaginationSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    page = fields.Integer(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Integer(load_default=20, validate=validate.Range(1, 100))
    status = fields.String(load_default=None)
