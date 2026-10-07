import time
from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import User
from app.utils.time import utcnow
from tests.conftest import PUNE, add_contact, register


def _trigger(client, **payload):
    return client.post("/api/sos/trigger", json=payload)


def test_sos_end_to_end(client, user, outbox):
    add_contact(client, name="Mom", phone="9123456780")
    add_contact(client, name="Riya", phone=None, email="riya@example.com")

    # Steps 1-8: trigger with GPS -> incident stored -> both contacts alerted.
    response = _trigger(client, **PUNE, note="Followed near bus stop")
    assert response.status_code == 201
    body = response.get_json()
    incident = body["incident"]
    assert body["created"] is True
    assert incident["status"] == "active" and incident["trigger"] == "sos"
    assert incident["gps_available"] is True and incident["location_source"] == "gps"
    assert [a["status"] for a in body["alerts"]] == ["sent", "sent"]
    assert {a["recipient"] for a in body["alerts"]} == {"+919123456780", "riya@example.com"}

    assert len(outbox) == 2
    message = outbox[0]["body"]
    assert "EMERGENCY ALERT" in message
    assert "https://www.google.com/maps/search/?api=1&query=18.520400,73.856700" in message
    assert incident["tracking_url"] in message

    # Step 7: live tracking - contacts see the path grow.
    token = incident["tracking_url"].rsplit("/", 1)[1]
    moved = client.post(f"/api/sos/{incident['id']}/location", json={"lat": 18.5210, "lng": 73.8570})
    assert moved.status_code == 201
    track = client.get(f"/api/track/{token}").get_json()
    assert track["status"] == "active"
    assert track["path"] == [[18.5204, 73.8567], [18.521, 73.857]]
    assert track["latest"]["lat"] == 18.521
    assert track["name"] == user["name"].split()[0]

    page = client.get(f"/track/{token}")
    assert page.status_code == 200
    assert "Content-Security-Policy" in page.headers

    # Pressing SOS again is idempotent - no second alert storm.
    again = _trigger(client, **PUNE)
    assert again.status_code == 200
    assert again.get_json()["created"] is False
    assert again.get_json()["incident"]["id"] == incident["id"]
    assert len(outbox) == 2

    # Step 9: user cancels -> all-clear to the same contacts, tracking stops.
    cancelled = client.post(f"/api/sos/{incident['id']}/cancel", json={"reason": "safe"})
    assert cancelled.status_code == 200
    assert cancelled.get_json()["incident"]["status"] == "resolved"
    assert [a["kind"] for a in cancelled.get_json()["alerts"]] == ["all_clear", "all_clear"]
    assert "ALL CLEAR" in outbox[-1]["body"]

    ended = client.get(f"/api/track/{token}").get_json()
    assert ended["status"] == "resolved"
    assert ended["latest"] is None and ended["path"] == []

    assert client.post(f"/api/sos/{incident['id']}/cancel", json={}).status_code == 409
    late = client.post(f"/api/sos/{incident['id']}/location", json={"lat": 18.5, "lng": 73.8})
    assert late.status_code == 409


def test_gps_unavailable_falls_back_to_last_known_location(client, user):
    add_contact(client)
    client.post("/api/location", json=PUNE)

    response = _trigger(client)
    assert response.status_code == 201
    incident = response.get_json()["incident"]
    assert incident["gps_available"] is False
    assert incident["location_source"] == "last_known"
    assert incident["start_location"] == {"lat": PUNE["lat"], "lng": PUNE["lng"]}
    assert any("last known" in w for w in response.get_json()["warnings"])


def test_stale_location_is_not_used_and_late_fix_sends_update(app, client, user, outbox):
    add_contact(client)
    client.post("/api/location", json=PUNE)
    with app.app_context():
        record = db.session.get(User, user["id"])
        record.last_location_at = utcnow() - timedelta(minutes=app.config["LOCATION_STALE_MINUTES"] + 1)
        db.session.commit()

    response = _trigger(client)
    incident = response.get_json()["incident"]
    assert incident["location_source"] == "none" and incident["start_location"] is None
    assert "not available yet" in outbox[-1]["body"]

    fix = client.post("/api/location", json={"lat": 18.53, "lng": 73.85})
    assert fix.get_json()["tracking_incident_id"] == incident["id"]
    assert outbox[-1]["kind"] == "update"
    assert "18.530000,73.850000" in outbox[-1]["body"]

    detail = client.get(f"/api/incidents/{incident['id']}").get_json()["incident"]
    assert detail["gps_available"] is True
    assert [a["kind"] for a in detail["alerts"]] == ["emergency", "update"]


def test_sos_without_contacts_still_records_incident(client, user):
    response = _trigger(client, **PUNE)
    assert response.status_code == 201
    assert response.get_json()["alerts"] == []
    assert any("No emergency contacts" in w for w in response.get_json()["warnings"])


def test_failing_channel_does_not_block_others(app, client, user):
    app.config["ALERT_CHANNELS"] = ["console", "email"]  # SMTP_HOST is empty -> email fails
    add_contact(client, email="mom@example.com")
    alerts = _trigger(client, **PUNE).get_json()["alerts"]
    by_channel = {a["channel"]: a for a in alerts}
    assert by_channel["console"]["status"] == "sent"
    assert by_channel["email"]["status"] == "failed"
    assert "SMTP_HOST" in by_channel["email"]["error"]


def test_incident_history_and_isolation(client, user, other_client):
    add_contact(client)
    first = _trigger(client, **PUNE).get_json()["incident"]
    client.post(f"/api/sos/{first['id']}/cancel", json={"reason": "false_alarm"})
    second = _trigger(client, **PUNE).get_json()["incident"]

    listing = client.get("/api/incidents?per_page=1").get_json()
    assert listing["total"] == 2 and listing["pages"] == 2
    assert listing["incidents"][0]["id"] == second["id"]

    false_alarms = client.get("/api/incidents?status=false_alarm").get_json()["incidents"]
    assert [i["id"] for i in false_alarms] == [first["id"]]
    assert client.get("/api/incidents?status=bogus").status_code == 422

    detail = client.get(f"/api/incidents/{first['id']}").get_json()["incident"]
    assert len(detail["locations"]) == 1 and len(detail["alerts"]) == 2  # emergency + all-clear

    assert other_client.get(f"/api/incidents/{first['id']}").status_code == 404
    assert other_client.post(f"/api/sos/{second['id']}/cancel", json={}).status_code == 404

    active = client.get("/api/sos/active").get_json()["incident"]
    assert active["id"] == second["id"]


def test_alert_history_survives_contact_deletion(client, user):
    contact = add_contact(client)
    incident = _trigger(client, **PUNE).get_json()["incident"]
    assert client.delete(f"/api/contacts/{contact['id']}").status_code == 204

    alerts = client.get(f"/api/incidents/{incident['id']}/alerts").get_json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["contact_id"] is None and alerts[0]["contact_name"] == "Mom"


def test_invalid_coordinates_and_unknown_tracking_token(client, user):
    assert _trigger(client, lat=123, lng=73.8).status_code == 422
    assert _trigger(client, lat=18.5).status_code == 422
    assert client.get("/api/track/not-a-real-token").status_code == 404
    assert client.get("/track/not-a-real-token").status_code == 404


def test_async_alert_delivery(tmp_path):
    app = create_app("testing", {"ALERT_ASYNC": True,
                                 "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'async.db').as_posix()}"})
    with app.app_context():
        db.create_all()
    client = app.test_client()
    register(client)
    add_contact(client)

    body = _trigger(client, **PUNE).get_json()
    assert [a["status"] for a in body["alerts"]] == ["queued"]  # SOS returns before delivery

    deadline = time.monotonic() + 5
    statuses = []
    while time.monotonic() < deadline:
        alerts = client.get(f"/api/incidents/{body['incident']['id']}/alerts").get_json()["alerts"]
        statuses = [a["status"] for a in alerts]
        if statuses == ["sent"]:
            break
        time.sleep(0.05)
    assert statuses == ["sent"]
    assert len(app.extensions["alert_outbox"]) == 1
    with app.app_context():
        db.engine.dispose()
