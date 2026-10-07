import pytest

from app.services.voice_service import match_transcript
from tests.conftest import PUNE, add_contact

PHRASES = ["help me", "bachao", "emergency", "बचाओ"]


@pytest.mark.parametrize("transcript, expected", [
    ("Help me!", "help me"),
    ("please someone help me now", "help me"),
    ("BACHAO bachao", "bachao"),
    ("help mee", "help me"),       # recogniser garbled under stress
    ("बचाओ!", "बचाओ"),              # Hindi in Devanagari
])
def test_transcript_matches(transcript, expected):
    result = match_transcript(transcript, PHRASES, threshold=0.8)
    assert result.matched and result.phrase == expected


@pytest.mark.parametrize("transcript", ["hello there", "help", "what time is it", ""])
def test_transcript_does_not_match(transcript):
    assert not match_transcript(transcript, PHRASES, threshold=0.8).matched


def test_verify_triggers_voice_emergency(client, user, outbox):
    add_contact(client)
    response = client.post("/api/voice/verify", json={"transcript": "please help me", "confidence": 0.9, **PUNE})
    assert response.status_code == 201
    body = response.get_json()
    assert body["verified"] is True and body["matched_phrase"] == "help me"
    assert body["incident"]["trigger"] == "voice"
    assert "voice emergency command" in outbox[-1]["body"]


def test_verify_without_match_or_with_low_confidence(client, user):
    no_match = client.post("/api/voice/verify", json={"transcript": "see you tomorrow"}).get_json()
    assert no_match["verified"] is False and no_match["reason"] == "no_match"

    unsure = client.post("/api/voice/verify", json={"transcript": "help me", "confidence": 0.2}).get_json()
    assert unsure["verified"] is False and unsure["reason"] == "low_confidence"

    assert client.get("/api/sos/active").get_json()["incident"] is None


def test_custom_phrases(client, user):
    added = client.post("/api/voice/phrases", json={"phrase": "Red Umbrella"})
    assert added.status_code == 201
    assert client.post("/api/voice/phrases", json={"phrase": "red umbrella!"}).status_code == 409

    response = client.post("/api/voice/verify", json={"transcript": "uh red umbrella"})
    assert response.get_json()["matched_phrase"] == "Red Umbrella"

    assert client.delete(f"/api/voice/phrases/{added.get_json()['phrase']['id']}").status_code == 204
