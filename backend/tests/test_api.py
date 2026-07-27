from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_verify_correct_step():
    response = client.post(
        "/verify",
        json={"step_id": "step-1", "text": "2*x + 6 = 14", "context": ["x + 3 = 7"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "correct"
    assert body["step_id"] == "step-1"
    assert body["confidence"] == 1.0
    assert body["source"] == "sympy"


def test_verify_incorrect_step_carries_a_fix():
    response = client.post(
        "/verify",
        json={"step_id": "step-2", "text": "2*x + 5 = 14", "context": ["2*x + 6 = 14"]},
    )
    body = response.json()
    assert body["status"] == "incorrect"
    assert body["fix"]


def test_first_step_has_no_reference():
    body = client.post(
        "/verify", json={"step_id": "s", "text": "x + 3 = 7", "context": []}
    ).json()
    assert body["status"] == "correct"
    assert "Starting line" in body["short"]


def test_blank_context_entries_are_skipped():
    body = client.post(
        "/verify",
        json={"step_id": "s", "text": "x = 4", "context": ["x + 3 = 7", "  ", ""]},
    ).json()
    assert body["status"] == "correct"


def test_oversized_text_is_rejected_by_validation():
    response = client.post(
        "/verify", json={"step_id": "s", "text": "x" * 5000, "context": []}
    )
    assert response.status_code == 422


def test_websocket_roundtrip():
    with client.websocket_connect("/ws/verify") as ws:
        ws.send_json({"step_id": "a", "text": "x + 3 = 7", "context": []})
        assert ws.receive_json()["status"] == "correct"

        ws.send_json({"step_id": "b", "text": "x = 5", "context": ["x + 3 = 7"]})
        second = ws.receive_json()
        assert second["status"] == "incorrect"
        assert second["step_id"] == "b"


def test_websocket_rejects_malformed_payload_without_closing():
    with client.websocket_connect("/ws/verify") as ws:
        ws.send_json({"nonsense": True})
        assert ws.receive_json()["type"] == "error"

        # The connection survives — the next step still works.
        ws.send_json({"step_id": "c", "text": "x = 4", "context": ["x + 3 = 7"]})
        assert ws.receive_json()["status"] == "correct"
