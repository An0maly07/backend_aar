from app import create_app
from app.extensions import db
from tests.conftest import register


def test_register_logs_in_and_seeds_trigger_phrases(client):
    user = register(client, phone="98765 43210", email="  Priya@Example.com ")
    assert user["phone"] == "+919876543210"
    assert user["email"] == "priya@example.com"
    assert "password" not in user and "password_hash" not in user

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["active_incident"] is None

    phrases = [p["phrase"] for p in client.get("/api/voice/phrases").get_json()["phrases"]]
    assert phrases == ["help me", "bachao", "emergency"]


def test_register_rejects_duplicates_across_phone_formats(app, client):
    register(client, email="a@example.com", phone="+91 98765 43210")
    other = app.test_client()
    dup_email = other.post("/api/auth/register", json={
        "name": "Bee", "email": "A@example.com", "phone": "9999999999", "password": "password1"})
    assert dup_email.status_code == 409
    assert dup_email.get_json()["error"]["code"] == "email_taken"

    dup_phone = other.post("/api/auth/register", json={
        "name": "Bee", "email": "b@example.com", "phone": "09876543210", "password": "password1"})
    assert dup_phone.status_code == 409
    assert dup_phone.get_json()["error"]["code"] == "phone_taken"


def test_register_validation_errors(client):
    response = client.post("/api/auth/register", json={
        "name": "A", "email": "not-an-email", "phone": "123", "password": "short"})
    assert response.status_code == 422
    details = response.get_json()["error"]["details"]
    assert set(details) == {"name", "email", "phone", "password"}


def test_login_with_email_or_phone_and_logout(app, client):
    register(client, email="login@example.com", phone="9811111111")
    client.post("/api/auth/logout", json={})
    assert client.get("/api/auth/me").status_code == 401

    by_email = client.post("/api/auth/login", json={"email": "LOGIN@example.com", "password": "s3cure-pass"})
    assert by_email.status_code == 200

    fresh = app.test_client()
    by_phone = fresh.post("/api/auth/login", json={"phone": "+919811111111", "password": "s3cure-pass"})
    assert by_phone.status_code == 200
    assert fresh.get("/api/auth/me").status_code == 200


def test_login_failures_are_indistinguishable(client):
    register(client, email="real@example.com")
    client.post("/api/auth/logout", json={})
    wrong_pw = client.post("/api/auth/login", json={"email": "real@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.get_json() == unknown.get_json()


def test_login_needs_exactly_one_identifier(client):
    response = client.post("/api/auth/login", json={"password": "x"})
    assert response.status_code == 422


def test_protected_routes_return_json_401(client):
    response = client.get("/api/contacts")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_writes_require_json_content_type(client):
    response = client.post("/api/auth/login", data="email=a@b.c&password=x",
                           content_type="application/x-www-form-urlencoded")
    assert response.status_code == 415


def test_malformed_json_is_rejected(client):
    response = client.post("/api/auth/login", data="{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "malformed_json"


def test_login_is_rate_limited():
    app = create_app("testing", {"RATELIMIT_ENABLED": True, "AUTH_RATE_LIMIT": "3 per minute"})
    with app.app_context():
        db.create_all()
        client = app.test_client()
        codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "pw"}).status_code
                 for _ in range(4)]
        db.drop_all()
    assert codes == [401, 401, 401, 429]


def test_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin"
    assert response.headers["Cache-Control"] == "no-store"
