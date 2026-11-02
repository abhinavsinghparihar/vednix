"""Regression tests for persistence, rotation, and honest attachment errors."""
import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from ai_engine.engine import AttachmentRef
from core.crypto import load_or_create_secret
from main import create_app
from memory.db import init_schema
from services.users import AuthError, UserService
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_postgres_schema_never_executes_sqlite_fts_ddl():
    class Connection:
        async def run_sync(self, function):
            assert function is not None
        async def execute(self, statement):
            raise AssertionError(f"SQLite SQL issued on PostgreSQL: {statement}")
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    class URL:
        def get_backend_name(self):
            return "postgresql"
    class Engine:
        url = URL()
        def begin(self):
            return Connection()
    assert await init_schema(Engine()) is False


@pytest.mark.asyncio
async def test_concurrent_refresh_only_one_rotation_succeeds(db, tmp_path):
    users = UserService(db[1], load_or_create_secret(tmp_path))
    user = await users.register(username="raceuser", password="password-123", ip="test")
    initial = await users.issue_session_for(user, remember=True, device_label="test")
    results = await asyncio.gather(
        users.refresh(refresh_token=initial.refresh_token),
        users.refresh(refresh_token=initial.refresh_token), return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 1
    assert len([r for r in results if isinstance(r, AuthError)]) == 1
    assert (await users.refresh(refresh_token=successes[0].refresh_token)).session_id == initial.session_id


def test_short_session_does_not_gain_long_cookie_on_refresh(settings):
    with TestClient(create_app(settings=settings)) as client:
        registered = client.post('/api/auth/register', json={'username': 'shortcookie', 'password': 'password-123'}).json()
        client.post('/api/auth/logout', headers={'X-CSRF-Token': registered['csrf_token']})
        login = client.post('/api/auth/login', json={'username': 'shortcookie', 'password': 'password-123', 'remember': False}).json()
        refreshed = client.post('/api/auth/refresh', headers={'X-CSRF-Token': login['csrf_token']})
        assert refreshed.status_code == 200
        cookie = next(c for c in client.cookies.jar if c.name == 'vednix_rt')
        import time
        assert 0 < cookie.expires - time.time() <= timedelta(hours=12).total_seconds()


@pytest.mark.asyncio
async def test_unreadable_document_does_not_get_sent_to_model(core, memory, files_store):
    row = await files_store.save('empty.txt', 'text/plain', b'   ')
    conv = await memory.create_conversation()
    llm = FakeLLM()
    engine_session = core(llm, files=files_store).create_session(memory, conv.id)
    async with files_store._sessions() as db:
        stored = await db.get(type(row), row.id)
        stored.text_path = None
        await db.commit()
    reply = ''.join([part async for part in engine_session.stream_reply('Summarize', attachments=[
        AttachmentRef(id=row.id, name=row.name, kind=row.kind, size=row.size),
    ])])
    assert engine_session.last_error['code'] == 'ATTACHMENT_READ_FAILED'
    assert 'could not read' in reply
    assert not llm.calls
    assert [m.role for m in await memory.list_messages(conv.id)] == ['user']


def test_websocket_accepts_access_token_without_url_query(settings):
    from tests.conftest import FakeLLM
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        created = client.post('/api/auth/register', json={'username': 'socketuser', 'password': 'password-123'})
        token = created.json()['access_token']
        with client.websocket_connect('/ws/chat', subprotocols=['vednix', f'vednix-auth.{token}']) as ws:
            assert ws.accepted_subprotocol == 'vednix'
            ws.send_json({'type': 'ping'})
            assert ws.receive_json()['type'] == 'pong'


def test_websocket_cannot_send_after_logout(settings):
    from starlette.websockets import WebSocketDisconnect
    from tests.conftest import FakeLLM
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        created = client.post('/api/auth/register', json={'username': 'revokedsocket', 'password': 'password-123'}).json()
        with client.websocket_connect('/ws/chat', subprotocols=['vednix', f"vednix-auth.{created['access_token']}"]) as ws:
            assert client.post('/api/auth/logout', headers={'X-CSRF-Token': created['csrf_token']}).status_code == 200
            ws.send_json({'type': 'user_message', 'content': 'should not be processed'})
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4401
