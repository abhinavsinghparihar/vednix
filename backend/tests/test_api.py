"""
End-to-end API tests: REST + the WebSocket streaming protocol.

Covers: streaming frames, persistence, busy guard (audit B5 web analog),
cancel semantics, auto-titling, and the language override path (§8).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from main import create_app
from tests.conftest import FakeLLM, SlowLLM


@pytest.fixture
def factory(settings):
    def make(llm=None) -> TestClient:
        return TestClient(create_app(settings=settings, llm_client=llm or FakeLLM()))
    return make


def read_until(ws, frame_type: str, max_frames: int = 80) -> list[dict]:
    frames: list[dict] = []
    for _ in range(max_frames):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") == frame_type:
            return frames
    raise AssertionError(f"never received {frame_type!r}; saw {[f.get('type') for f in frames]}")


# --- REST -----------------------------------------------------------------------

def test_health_and_models(factory):
    with factory() as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok" and health["ollama_available"] is True
        # brand signature: primary brand + creator, both configurable
        assert health["assistant"] == "Vednix AI"
        assert health["creator"] == "Abhinav Singh"
        models = client.get("/api/models").json()
        assert "fake-model" in models["available"]


def test_conversation_rest_crud(factory):
    with factory() as client:
        created = client.post("/api/conversations", json={"language": "hi"}).json()
        assert created["language"] == "hi"

        listed = client.get("/api/conversations").json()
        assert len(listed) == 1

        detail = client.get(f"/api/conversations/{created['id']}").json()
        assert detail["messages"] == []

        updated = client.patch(f"/api/conversations/{created['id']}", json={"pinned": True}).json()
        assert updated["pinned"] is True

        assert client.delete(f"/api/conversations/{created['id']}").status_code == 204
        assert client.get(f"/api/conversations/{created['id']}").status_code == 404


def test_memory_rest(factory):
    with factory() as client:
        created = client.post("/api/memory", json={"content": "deploy on Friday", "kind": "task"}).json()
        assert created["id"] >= 1
        found = client.get("/api/memory", params={"query": "friday"}).json()
        assert len(found) == 1
        assert client.delete(f"/api/memory/{created['id']}").status_code == 204


# --- WebSocket -------------------------------------------------------------------

def test_ws_full_streaming_flow_and_persistence(factory, settings):
    with factory() as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "namaste, kaise ho?"})
            frames = read_until(ws, "message_done")
            types = [f["type"] for f in frames]

            assert "conversation_created" in types
            assert "message_started" in types
            assert types.count("token") == 3  # FakeLLM streams 3 chunks
            states = [f["state"] for f in frames if f["type"] == "state_changed"]
            assert "THINKING" in states and "SPEAKING" in states and states[-1] == "IDLE"

            # auto-title comes from FakeLLM.chat right after
            title_frames = read_until(ws, "title_updated")
            conv_id = next(f["conversation_id"] for f in frames if f["type"] == "conversation_created")
            assert title_frames[-1]["conversation_id"] == conv_id
            assert title_frames[-1]["title"] == "Test Conversation Title"

        detail = client.get(f"/api/conversations/{conv_id}").json()
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
        assert detail["messages"][1]["content"] == "Hello from Vednix!"


def test_ws_plugin_message_reports_plugins(factory):
    with factory() as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "what time is it"})
            frames = read_until(ws, "message_done")
            done = frames[-1]
            assert done["plugins"] == ["time"]
            tokens = "".join(f["content"] for f in frames if f["type"] == "token")
            assert "**" in tokens  # time plugin markdown


def test_ws_validation_and_length_guard(factory, settings):
    with factory() as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "x" * (settings.max_message_chars + 1)})
            frames = read_until(ws, "error")
            assert frames[-1]["code"] == "too_long"


def test_ws_busy_guard_and_cancel(settings):
    slow = SlowLLM()
    with TestClient(create_app(settings=settings, llm_client=slow)) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "long answer please"})
            first_token = read_until(ws, "token")
            conv_id = next(
                f["conversation_id"] for f in reversed(first_token) if f["type"] == "conversation_created"
            )

            # second message while streaming → busy
            ws.send_json({"type": "user_message", "content": "another one"})
            busy = read_until(ws, "error")
            assert busy[-1]["code"] == "busy"

            # cancel → partial persisted, done(cancelled=True)
            ws.send_json({"type": "cancel"})
            done = read_until(ws, "message_done")[-1]
            assert done["cancelled"] is True

        detail = client.get(f"/api/conversations/{conv_id}").json()
        roles = [m["role"] for m in detail["messages"]]
        assert roles == ["user", "assistant"]
        assert detail["messages"][1]["content"].endswith("*(stopped)*")


def test_ws_language_override_reaches_system_prompt(settings):
    llm = FakeLLM()
    from main import create_app as _create
    with TestClient(_create(settings=settings, llm_client=llm)) as client:
        conv = client.post("/api/conversations", json={"language": "auto"}).json()
        client.patch(f"/api/conversations/{conv['id']}", json={"language": "hi"})
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "conversation_id": conv["id"], "content": "hello"})
            read_until(ws, "message_done")
    assert "FORCE LANGUAGE" in llm.calls[0][0]["content"]


def test_ws_ping_pong(factory):
    with factory() as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}


def test_ws_temperature_override_reaches_llm(settings):
    llm = FakeLLM()
    with TestClient(create_app(settings=settings, llm_client=llm)) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "hello", "temperature": 0.05})
            read_until(ws, "message_done")
    assert llm.temperatures == [0.05]  # control-panel slider is real, not decorative


# --- Phase 4: uploads + knowledge over the real API --------------------------------

def test_upload_rest_validation_and_extraction(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        # happy path
        resp = client.post(
            "/api/uploads",
            files=[("files", ("facts.txt", b"Vednix uploads work.", "text/plain"))],
        )
        assert resp.status_code == 201
        uploaded = resp.json()[0]
        assert uploaded["kind"] == "text" and uploaded["extracted_chars"] > 0

        preview = client.get(f"/api/uploads/{uploaded['id']}/text").json()
        assert "Vednix uploads work." in preview["text"]

        # unsupported type rejected with a user-readable reason
        bad = client.post("/api/uploads", files=[("files", ("run.exe", b"MZ", "application/octet-stream"))])
        assert bad.status_code == 422


def test_ws_chat_with_attachment(settings):
    llm = FakeLLM()
    with TestClient(create_app(settings=settings, llm_client=llm)) as client:
        uploaded = client.post(
            "/api/uploads",
            files=[("files", ("codes.txt", b"The launch code is KAVACH-1.", "text/plain"))],
        ).json()[0]
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message",
                "content": "what is the launch code?",
                "attachments": [uploaded["id"]],
            })
            frames = read_until(ws, "message_done")
            assert frames[-1]["cancelled"] is False
    fed = llm.calls[0][-1]["content"]
    assert "KAVACH-1" in fed and "### File: codes.txt" in fed


def test_knowledge_rest_cycle(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        doc = client.post("/api/knowledge/documents", json={
            "title": "Meeting Notes", "text": "The client call moved to Tuesday 3 PM. " * 8,
        })
        assert doc.status_code == 201
        doc_id = doc.json()["id"]
        assert doc.json()["chunk_count"] >= 1

        found = client.get("/api/knowledge/search", params={"q": "client call"}).json()
        assert found["hits"] and found["hits"][0]["document"] == "Meeting Notes"

        assert client.get("/api/knowledge/documents").json()[0]["id"] == doc_id
        assert client.delete(f"/api/knowledge/documents/{doc_id}").status_code == 204
