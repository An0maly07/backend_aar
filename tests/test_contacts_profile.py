from tests.conftest import add_contact, register


def test_contact_crud(client, user):
    first = add_contact(client, name="Mom", phone="9123456789")
    second = add_contact(client, name="Riya", phone=None, email="riya@example.com")
    assert first["phone"] == "+919123456789"
    assert (first["priority"], second["priority"]) == (1, 2)

    updated = client.patch(f"/api/contacts/{second['id']}", json={"priority": 1, "relation": "best friend"})
    assert updated.status_code == 200
    assert updated.get_json()["contact"]["relation"] == "best friend"

    listed = client.get("/api/contacts").get_json()["contacts"]
    assert [c["name"] for c in listed] == ["Mom", "Riya"]  # ties broken by id

    assert client.delete(f"/api/contacts/{first['id']}").status_code == 204
    assert client.get(f"/api/contacts/{first['id']}").status_code == 404


def test_contact_needs_phone_or_email(client, user):
    response = client.post("/api/contacts", json={"name": "Nobody"})
    assert response.status_code == 422

    contact = add_contact(client, email=None)
    cleared = client.patch(f"/api/contacts/{contact['id']}", json={"phone": None})
    assert cleared.status_code == 422


def test_duplicate_contact_phone_conflicts(client, user):
    add_contact(client, phone="9000000001")
    response = client.post("/api/contacts", json={"name": "Dup", "phone": "+91 90000 00001"})
    assert response.status_code == 409


def test_contact_limit(app, client, user):
    app.config["MAX_CONTACTS"] = 2
    add_contact(client)
    add_contact(client)
    response = client.post("/api/contacts", json={"name": "Third", "email": "t@example.com"})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "contact_limit"


def test_users_cannot_see_each_others_contacts(client, user, other_client):
    contact = add_contact(client)
    assert other_client.get(f"/api/contacts/{contact['id']}").status_code == 404
    assert other_client.delete(f"/api/contacts/{contact['id']}").status_code == 404
    assert other_client.get("/api/contacts").get_json()["contacts"] == []


def test_profile_update_and_password_change(app, client):
    register(client, phone="9888888888")
    other = app.test_client()
    register(other, phone="9777777777")

    taken = other.patch("/api/profile", json={"phone": "9888888888"})
    assert taken.status_code == 409

    ok = client.patch("/api/profile", json={"custom_message": "I'm walking home via MG Road",
                                            "baseline_heart_rate": 68})
    assert ok.status_code == 200
    assert ok.get_json()["user"]["baseline_heart_rate"] == 68

    wrong = client.post("/api/profile/password", json={"current_password": "bad", "new_password": "newpass123"})
    assert wrong.status_code == 401
    changed = client.post("/api/profile/password",
                          json={"current_password": "s3cure-pass", "new_password": "newpass123"})
    assert changed.status_code == 200


def test_dashboard(client, user):
    data = client.get("/api/dashboard").get_json()
    assert data["ready"] is False
    add_contact(client)
    data = client.get("/api/dashboard").get_json()
    assert data["ready"] is True
    assert data["contacts_count"] == 1
    assert data["active_incident"] is None and data["pending_risk_check"] is None
