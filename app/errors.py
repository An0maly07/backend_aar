"""API error types and the JSON error handlers.

Every error response has the same shape::

    {"error": {"code": "not_found", "message": "...", "details": {...}}}
"""
import logging

from flask import Flask, jsonify
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class APIError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class Unauthorized(APIError):
    status_code = 401
    code = "unauthorized"


class NotFound(APIError):
    status_code = 404
    code = "not_found"


class Conflict(APIError):
    status_code = 409
    code = "conflict"


class Unprocessable(APIError):
    status_code = 422
    code = "validation_error"


def error_response(status: int, code: str, message: str, details: dict | None = None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return error_response(err.status_code, err.code, err.message, err.details)

    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        return error_response(422, "validation_error", "Request validation failed.", err.messages)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        code = (err.name or "error").lower().replace(" ", "_")
        response = error_response(err.code or 500, code, err.description or err.name)
        return response

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        log.exception("Unhandled error")
        return error_response(500, "internal_error", "Something went wrong on our side.")
