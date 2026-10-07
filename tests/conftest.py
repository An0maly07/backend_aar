import itertools

import pytest

from app import create_app
from app.extensions import db

_counter = itertools.count(1)


@pytest.fixture
def app():
    # No app context is held open during the test: each request gets its own,
    # exactly like production (otherwise `g` and the session leak between clients).
    app = create_app("testing")
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def ctx(app):
    """For tests that touch the database directly."""
    with app.app_context():
        yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def outbox(app):
    return app.extensions["alert_outbox"]


def register(client, **overrides):
    n = next(_counter)
    payload = {
        "name": f"Asha Test{n}",
        "email": f"asha{n}@example.com",
        "phone": f"98765{n:05d}",
        "password": "s3cure-pass",
    }
    payload.update(overrides)
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["user"]


def add_contact(client, **overrides):
    payload = {"name": "Mom", "phone": f"91234{next(_counter):05d}", "relation": "mother"}
    payload.update(overrides)
    response = client.post("/api/contacts", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["contact"]


@pytest.fixture
def user(client):
    """A logged-in user (the test client keeps the session cookie)."""
    return register(client)


@pytest.fixture
def other_client(app):
    other = app.test_client()
    register(other)
    return other


PUNE = {"lat": 18.5204, "lng": 73.8567, "accuracy_m": 12.0}
