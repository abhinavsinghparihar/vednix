"""Stay signed in — a device that signs in once is not signed out by time.

The contract:

  * a remembered device gets a long, *sliding* session: every refresh pushes
    the expiry forward, so an active device never reaches the ceiling;
  * the refresh cookie lives exactly as long as the server-side session;
  * an explicit sign-out, a revoked session, or a password change still ends
    it immediately — "never auto-logout" is not "cannot log out";
  * operators can tune the ceiling (VEDNIX_SESSION_DAYS) without code changes.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core.crypto import load_or_create_secret
from main import create_app
from memory.models import AuthSession
from services.users import REFRESH_TTL, UserService


def _secret(settings) -> bytes:
    return load_or_create_secret(
        pathlib.Path(settings.database_url.replace("sqlite+aiosqlite:///", "")).parent
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _bearer(body: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {body['access_token']}"}


def _refresh_cookie_lifetime(client) -> timedelta:
    rt = next(c for c in client.cookies.jar if c.name == "vednix_rt")
    return _aware(datetime.fromtimestamp(rt.expires, timezone.utc)) - datetime.now(timezone.utc)


def test_registering_a_device_keeps_it_signed_in_for_years(settings):
    with TestClient(create_app(settings=settings)) as client:
        created = client.post(
            "/api/auth/register",
            json={"username": "owner1", "password": "password-123", "display_name": "Owner"},
        )
        assert created.status_code == 201, created.text

        sessions = client.get("/api/auth/sessions", headers=_bearer(created.json())).json()
        assert len(sessions) == 1
        assert sessions[0]["remember"] is True
        assert _refresh_cookie_lifetime(client) > timedelta(days=settings.session_days - 1)


def test_session_only_sign_in_still_expires_with_the_day(settings):
    with TestClient(create_app(settings=settings)) as client:
        created = client.post(
            "/api/auth/register", json={"username": "owner2", "password": "password-123"},
        )
        client.post(
            "/api/auth/logout",
            headers={**_bearer(created.json()), "X-CSRF-Token": created.json()["csrf_token"]},
        )
        signed_in = client.post(
            "/api/auth/login",
            json={"username": "owner2", "password": "password-123", "remember": False},
        )
        assert signed_in.status_code == 200, signed_in.text
        rows = client.get("/api/auth/sessions", headers=_bearer(signed_in.json())).json()
        assert rows[0]["remember"] is False
        assert _refresh_cookie_lifetime(client) < timedelta(hours=13)


def test_operator_can_configure_the_session_ceiling(settings):
    settings = settings.model_copy(update={"session_days": 45})
    with TestClient(create_app(settings=settings)) as client:
        client.post("/api/auth/register", json={"username": "owner3", "password": "password-123"})
        lifetime = _refresh_cookie_lifetime(client)
        assert timedelta(days=44) < lifetime <= timedelta(days=45, hours=1)


@pytest.mark.asyncio
async def test_every_refresh_slides_the_expiry_forward(db, settings):
    users = UserService(db[1], _secret(settings), remember_ttl=timedelta(days=3650))
    user = await users.register(username="slider", password="password-123", ip="tests")
    first = await users.issue_session_for(user, remember=True, device_label="laptop")

    # Simulate a session that is about to expire after months of use.
    async with db[1]() as db_session:
        session = await db_session.get(AuthSession, first.session_id)
        session.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        await db_session.commit()

    rotated = await users.refresh(refresh_token=first.refresh_token)
    async with db[1]() as db_session:
        session = await db_session.get(AuthSession, rotated.session_id)
        remaining = _aware(session.expires_at) - datetime.now(timezone.utc)
    assert remaining > timedelta(days=3640)

    # And the device is still live after the rotation.
    assert await users.access_session_active(rotated.session_id) is True


@pytest.mark.asyncio
async def test_explicit_sign_out_still_ends_the_long_session(db, settings):
    users = UserService(db[1], _secret(settings), remember_ttl=timedelta(days=3650))
    user = await users.register(username="leaver", password="password-123", ip="tests")
    tokens = await users.issue_session_for(user, remember=True, device_label="phone")

    await users.logout(refresh_token=tokens.refresh_token)

    assert await users.access_session_active(tokens.session_id) is False
    with pytest.raises(Exception):
        await users.refresh(refresh_token=tokens.refresh_token)


@pytest.mark.asyncio
async def test_session_only_fallback_stays_twelve_hours(db, settings):
    users = UserService(db[1], _secret(settings))
    user = await users.register(username="shortstay", password="password-123", ip="tests")
    tokens = await users.issue_session_for(user, remember=False, device_label="kiosk")
    async with db[1]() as db_session:
        session = await db_session.get(AuthSession, tokens.session_id)
        remaining = _aware(session.expires_at) - datetime.now(timezone.utc)
    assert remaining <= REFRESH_TTL
    assert users.remember_ttl > timedelta(days=365)


def test_csrf_bootstrap_reports_cookie_presence_without_caching(settings):
    with TestClient(create_app(settings=settings)) as client:
        guest = client.get("/api/auth/csrf")
        assert guest.status_code == 200
        assert guest.json()["has_session"] is False
        assert guest.headers["cache-control"] == "no-store"
        assert guest.json()["csrf_token"]
        client.post("/api/auth/register", json={"username": "cookiecheck", "password": "password-123"})
        assert client.get("/api/auth/csrf").json()["has_session"] is True


def test_reopened_browser_and_restarted_backend_restore_remembered_session(settings):
    with TestClient(create_app(settings=settings)) as client:
        registered = client.post(
            "/api/auth/register", json={"username": "returning", "password": "password-123"},
        )
        assert registered.status_code == 201
        # A fresh browser process loses the SPA's access token, but keeps
        # persistent cookies. A server restart must keep the session too.
        cookies = dict(client.cookies)

    with TestClient(create_app(settings=settings)) as reopened:
        reopened.cookies.update(cookies)
        bootstrap = reopened.get("/api/auth/csrf").json()
        assert bootstrap["has_session"] is True
        refreshed = reopened.post(
            "/api/auth/refresh", headers={"X-CSRF-Token": bootstrap["csrf_token"]},
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["user"]["username"] == "returning"
        assert reopened.get("/api/auth/me", headers=_bearer(refreshed.json())).status_code == 200
