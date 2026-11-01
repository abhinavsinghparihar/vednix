"""Phase 8 — the owner's admin console.

An explicitly provisioned owner administers the machine; the admin API is the owner exercising
that ownership: list every account (with live sessions), reset passwords,
revoke sessions, remove members. Members get 403, anonymous gets 401, and
the last owner is immortal — no-signup-no-entry means the door must never
brick itself.
"""

from __future__ import annotations

import anyio
import pytest
from fastapi.testclient import TestClient

from main import create_app



def _register(client: TestClient, username: str, password: str) -> dict:
    resp = client.post("/api/auth/register", json={
        "username": username, "password": password, "display_name": username.title(),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth(body: dict) -> dict:
    return {"Authorization": f"Bearer {body['access_token']}"}


def _refresh(client: TestClient):
    """Refresh via whatever session the shared cookie jar currently holds."""
    return client.post(
        "/api/auth/refresh",
        headers={"X-CSRF-Token": client.cookies.get("vednix_csrf") or ""},
    )


def test_owner_console_full_lifecycle(settings, promote_owner):
    with TestClient(create_app(settings=settings)) as client:
        _register(client, "abhinav", "owner-pass-1")
        owner = promote_owner(client, "abhinav", "owner-pass-1")
        member = _register(client, "ravi", "member-pass-1")  # jar ← ravi's session
        assert member["user"]["role"] == "member"  # public signup never grants admin
        ravi_id = member["user"]["id"]

        # --- the console table -------------------------------------------------
        listed = client.get("/api/admin/users", headers=_auth(owner)).json()["users"]
        assert [u["username"] for u in listed] == ["abhinav", "ravi"]
        assert all(u["role"] in ("owner", "member") for u in listed)
        assert all(u["live_sessions"] >= 1 for u in listed)

        # --- members are locked OUT of the console -----------------------------
        assert client.get("/api/admin/users", headers=_auth(member)).status_code == 403
        assert client.delete(f"/api/admin/users/{ravi_id}",
                             headers=_auth(member)).status_code == 403

        # --- reset a member's password ------------------------------------------
        ok = client.post(f"/api/admin/users/{ravi_id}/password",
                         json={"password": "fresh-pass-9"}, headers=_auth(owner))
        assert ok.status_code == 200
        # old password dies, the reset revoked every old session of theirs
        assert client.post("/api/auth/login",
                           json={"username": "ravi", "password": "member-pass-1"}).status_code == 401
        assert _refresh(client).status_code in (401, 403)
        # the new password opens the door again (jar ← ravi's fresh session)
        relogin = client.post("/api/auth/login",
                              json={"username": "ravi", "password": "fresh-pass-9"})
        assert relogin.status_code == 200

        # --- revoke sessions on demand ------------------------------------------
        revoked = client.post(f"/api/admin/users/{ravi_id}/revoke-sessions",
                              headers=_auth(owner))
        assert revoked.status_code == 200 and revoked.json()["revoked"] >= 1
        assert _refresh(client).status_code in (401, 403)

        # --- owner guards + member removal ---------------------------------------
        owner_id = owner["user"]["id"]
        assert client.delete(f"/api/admin/users/{owner_id}",
                             headers=_auth(owner)).status_code == 400  # never yourself
        assert client.delete(f"/api/admin/users/{ravi_id}",
                             headers=_auth(owner)).status_code == 200
        assert client.post("/api/auth/login",
                           json={"username": "ravi", "password": "fresh-pass-9"}).status_code == 401


def test_admin_anonymous_and_last_owner_protection(settings, promote_owner):
    with TestClient(create_app(settings=settings)) as client:
        # anonymous: the session lock answers before the admin gate even runs
        assert client.get("/api/admin/users").status_code in (401, 403)

        _register(client, "solo", "solo-pass-1")
        owner = promote_owner(client, "solo", "solo-pass-1")
        # service-level last-owner immortality (the HTTP layer redirects to a
        # self-delete 400 first, so this reaches straight into the service)
        with pytest.raises(PermissionError):
            anyio.run(client.app.state.users.admin_delete_user, owner["user"]["id"])


def test_first_public_signup_and_role_injection_never_grant_admin(settings):
    with TestClient(create_app(settings=settings)) as client:
        created = client.post("/api/auth/register", json={
            "username": "firstvisitor", "password": "member-pass-1", "role": "owner",
        })
        assert created.status_code == 201
        member = created.json()
        assert member["user"]["role"] == "member"
        headers = _auth(member)
        user_id = member["user"]["id"]
        assert client.get("/api/admin/users", headers=headers).status_code == 403
        assert client.post(f"/api/admin/users/{user_id}/password", headers=headers,
                           json={"password": "changed-pass-1"}).status_code == 403
        assert client.post(f"/api/admin/users/{user_id}/revoke-sessions", headers=headers).status_code == 403
        assert client.delete(f"/api/admin/users/{user_id}", headers=headers).status_code == 403


def test_separate_browser_does_not_inherit_owner_session(settings, promote_owner):
    app = create_app(settings=settings)
    with TestClient(app) as owner_browser:
        _register(owner_browser, "privateowner", "owner-pass-1")
        owner = promote_owner(owner_browser, "privateowner", "owner-pass-1")
        # Separate client with an empty cookie jar is another visitor.
        with TestClient(app) as visitor:
            assert visitor.get("/api/auth/csrf").json()["has_session"] is False
            assert visitor.get("/api/admin/users").status_code == 401
            member = _register(visitor, "regularvisitor", "member-pass-1")
            assert member["user"]["role"] == "member"
            assert visitor.get("/api/auth/me", headers=_auth(member)).json()["id"] != owner["user"]["id"]
            assert visitor.get("/api/admin/users", headers=_auth(member)).status_code == 403


def test_demoted_owner_token_cannot_use_admin_api(settings, promote_owner):
    from sqlalchemy import update
    from memory.db import create_engine_and_session
    from memory.models import User

    with TestClient(create_app(settings=settings)) as client:
        _register(client, "demoted", "owner-pass-1")
        owner = promote_owner(client, "demoted", "owner-pass-1")
        async def demote():
            engine, sessions = create_engine_and_session(settings.database_url)
            try:
                async with sessions() as db:
                    await db.execute(update(User).where(User.id == owner["user"]["id"]).values(role="member"))
                    await db.commit()
            finally:
                await engine.dispose()
        anyio.run(demote)
        assert client.get("/api/admin/users", headers=_auth(owner)).status_code == 403
