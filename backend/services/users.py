"""Accounts & sessions service — register, login (with brute-force damping),
refresh rotation with reuse detection, device management, profile updates.

Local-first honesty notes:
  - The app runs OPEN until the first account exists (single-user default,
    unchanged). Registering is the user's explicit opt-in to lock-screen mode.
  - "Email verification" as SaaS knows it needs SMTP, which an offline-first
    local app cannot guarantee. So: email is an OPTIONAL profile field; if
    VEDNIX_SMTP_* is ever configured a real mail path can hang off this seam.
    Until then the register endpoint verifies syntax only and marks nothing
    "pending" — no theater, no dead states.
"""

from __future__ import annotations

import re
import hashlib
import hmac
import secrets
import smtplib
from email.message import EmailMessage
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging import get_logger
from core.tokens import (
    TokenError,
    hash_password,
    issue_access_token,
    new_refresh_token,
    refresh_digest,
    verify_access_token,
    verify_password,
)
from memory.models import AuthSession, EmailOTP, User

logger = get_logger(__name__)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ACCESS_TTL = 20 * 60                    # 20 minutes
REFRESH_TTL = timedelta(hours=12)       # session ends when the OS day does…
REFRESH_TTL_REMEMBER = timedelta(days=30)  # …unless "remember me"

MAX_FAILED_ATTEMPTS = 5          # then a short lockout
LOCKOUT = timedelta(minutes=5)


def _aware(dt: datetime) -> datetime:
    """SQLite has no tz storage: DateTime(timezone=True) columns come back
    NAIVE. Coerce to UTC at the comparison site, never compare raw."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class AuthError(ValueError):
    """Public-facing auth failure (mapped to 401/422 by the route layer)."""


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    access_expires_in: int
    session_id: str


class UserService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], secret: bytes) -> None:
        self._sessions = sessions
        self._secret = secret
        # brute-force damping: ip → (failed count, lockout until)
        self._failures: dict[str, tuple[int, datetime]] = {}
        # auth_enabled() runs on EVERY request (middleware) — cache the count,
        # invalidate on register. No user-delete endpoint exists, so this is exact.
        self._count_cache: int | None = None

    # --- helpers ------------------------------------------------------------

    def _sign_access(self, user: User) -> tuple[str, int]:
        return (
            issue_access_token(
                self._secret, user_id=user.id, username=user.username,
                role=user.role, ttl_seconds=ACCESS_TTL,
            ),
            ACCESS_TTL,
        )

    @staticmethod
    def _norm(username: str) -> str:
        return username.strip().lower()

    def _check_lockout(self, ip: str) -> None:
        count, until = self._failures.get(ip, (0, datetime.min.replace(tzinfo=timezone.utc)))
        if count >= MAX_FAILED_ATTEMPTS and until > datetime.now(timezone.utc):
            raise AuthError("Too many failed attempts — try again in a few minutes.")

    def _record_failure(self, ip: str) -> None:
        count, _ = self._failures.get(ip, (0, datetime.min.replace(tzinfo=timezone.utc)))
        self._failures[ip] = (count + 1, datetime.now(timezone.utc) + LOCKOUT)

    def _clear_failures(self, ip: str) -> None:
        self._failures.pop(ip, None)

    # --- state ---------------------------------------------------------------

    async def user_count(self) -> int:
        if self._count_cache is not None:
            return self._count_cache
        async with self._sessions() as db:
            self._count_cache = int((await db.execute(select(func.count(User.id)))).scalar_one())
            return self._count_cache

    async def auth_enabled(self) -> bool:
        return (await self.user_count()) > 0

    # --- register --------------------------------------------------------------

    async def register(
        self, *, username: str, password: str, display_name: str = "",
        email: str | None = None, ip: str = "local",
    ) -> User:
        username = self._norm(username)
        if not USERNAME_RE.match(username):
            raise AuthError("Username must be 3-32 chars: letters, digits, _ . -")
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        if email:
            email = email.strip().lower()
            if not EMAIL_RE.match(email):
                raise AuthError("That email address doesn't look right.")
        self._check_lockout(ip)
        async with self._sessions() as db:
            exists = (await db.execute(select(User.id).where(User.username == username))).first()
            if exists:
                self._record_failure(ip)
                raise AuthError("That username is taken.")
            role = "owner" if await self.user_count() == 0 else "member"
            user = User(
                username=username, display_name=display_name.strip() or username,
                email=email, password_hash=hash_password(password), role=role,
            )
            db.add(user)
            await db.commit()
            self._count_cache = None  # invalidate the middleware fast-path
            logger.info("account registered: %s (role=%s)", username, role)
            return user

    async def request_email_otp(self, email: str, *, settings, ip: str = "local") -> None:
        email = email.strip().lower()
        if not EMAIL_RE.match(email):
            raise AuthError("Enter a valid email address.")
        # Avoid account enumeration: callers receive the same success response.
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = hmac.new(self._secret, code.encode(), hashlib.sha256).hexdigest()
        now = datetime.now(timezone.utc)
        async with self._sessions() as db:
            old = (await db.execute(select(EmailOTP).where(EmailOTP.email == email, EmailOTP.consumed == False))).scalars().all()
            for row in old: row.consumed = True
            db.add(EmailOTP(email=email, code_digest=digest, expires_at=now + timedelta(seconds=settings.otp_ttl_seconds)))
            await db.commit()
        if not (settings.smtp_host and settings.smtp_username and settings.smtp_password):
            raise AuthError("Email OTP is not configured. Add Gmail SMTP settings to backend/.env.")
        msg = EmailMessage()
        msg["Subject"] = "Your Vednix AI verification code"
        msg["From"] = settings.smtp_from or settings.smtp_username
        msg["To"] = email
        msg.set_content(f"Your Vednix AI verification code is {code}. It expires in 10 minutes. If you did not request it, ignore this email.")
        def send():
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_starttls: server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        try:
            import asyncio
            await asyncio.to_thread(send)
        except Exception as exc:
            logger.warning("OTP email delivery failed: %s", exc)
            raise AuthError("We could not send the verification email. Check SMTP settings.") from exc

    async def verify_email_otp(self, email: str, code: str) -> User:
        email = email.strip().lower(); code = code.strip()
        if not re.fullmatch(r"\d{6}", code): raise AuthError("Enter the 6-digit verification code.")
        async with self._sessions() as db:
            row = (await db.execute(select(EmailOTP).where(EmailOTP.email == email, EmailOTP.consumed == False).order_by(EmailOTP.created_at.desc()))).scalars().first()
            if row is None or row.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc): raise AuthError("Verification code expired. Request a new code.")
            row.attempts += 1
            if row.attempts > 5: row.consumed = True; await db.commit(); raise AuthError("Too many code attempts. Request a new code.")
            digest = hmac.new(self._secret, code.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(digest, row.code_digest): await db.commit(); raise AuthError("Incorrect verification code.")
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None: await db.commit(); raise AuthError("No Vednix account exists for this email. Create an account first.")
            row.consumed = True; await db.commit(); return user

    # --- login -----------------------------------------------------------------

    async def login(
        self, *, username: str, password: str, remember: bool,
        device_label: str, ip: str = "local",
    ) -> tuple[User, IssuedTokens]:
        username = self._norm(username)
        self._check_lockout(ip)
        async with self._sessions() as db:
            # identifier may be a username OR an email (the login field doesn't
            # force the user to remember which they typed; ambiguity = fail-closed)
            if "@" in username:
                rows = (await db.execute(select(User).where(User.email == username))).scalars().all()
                user = rows[0] if len(rows) == 1 else None
            else:
                user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            # constant-shape failure: same message whether user or password is wrong
            if user is None or not verify_password(password, user.password_hash):
                self._record_failure(ip)
                raise AuthError("Wrong username or password.")
            self._clear_failures(ip)
            return user, await self._issue_session(db, user, remember=remember, device_label=device_label)

    async def _issue_session(
        self, db: AsyncSession, user: User, *, remember: bool, device_label: str,
    ) -> IssuedTokens:
        refresh = new_refresh_token()
        ttl = REFRESH_TTL_REMEMBER if remember else REFRESH_TTL
        session = AuthSession(
            user_id=user.id, refresh_digest=refresh_digest(refresh),
            device_label=device_label[:160] or "This device",
            remember=remember, expires_at=datetime.now(timezone.utc) + ttl,
        )
        db.add(session)
        await db.commit()
        access, ttl_access = self._sign_access(user)
        return IssuedTokens(access, refresh, ttl_access, session.id)

    async def issue_session_for(
        self, user: User, *, remember: bool, device_label: str,
    ) -> IssuedTokens:
        """Open a session for an already-authenticated user (register →
        instant login; used by the register route)."""
        async with self._sessions() as db:
            return await self._issue_session(db, user, remember=remember, device_label=device_label)

    async def get_user_by_session(self, session_id: str) -> User | None:
        async with self._sessions() as db:
            session = await db.get(AuthSession, session_id)
            if session is None:
                return None
            return (await db.execute(select(User).where(User.id == session.user_id))).scalar_one_or_none()

    # --- refresh (rotating, reuse-detecting) -------------------------------------

    async def refresh(self, *, refresh_token: str, device_label: str = "") -> IssuedTokens:
        digest = refresh_digest(refresh_token)
        async with self._sessions() as db:
            session = (
                await db.execute(select(AuthSession).where(AuthSession.refresh_digest == digest))
            ).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if session is None:
                raise AuthError("Session not found — sign in again.")
            if session.revoked or _aware(session.expires_at) <= now:
                raise AuthError("Session expired — sign in again.")
            # rotate: this digest dies, a new one is born
            new_refresh = new_refresh_token()
            session.refresh_digest = refresh_digest(new_refresh)
            session.last_seen_at = now
            if device_label:
                session.device_label = device_label[:160]
            # sliding renewal on remembered sessions only
            if session.remember:
                session.expires_at = now + REFRESH_TTL_REMEMBER
            user = (await db.execute(select(User).where(User.id == session.user_id))).scalar_one()
            await db.commit()
            access, ttl_access = self._sign_access(user)
            return IssuedTokens(access, new_refresh, ttl_access, session.id)

    # --- access-token resolution (middleware seam) ---------------------------------

    def resolve_access_token(self, token: str) -> dict:
        return verify_access_token(self._secret, token)

    async def get_user(self, user_id: str) -> User | None:
        async with self._sessions() as db:
            return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    # --- logout / devices -----------------------------------------------------------

    async def logout(self, *, refresh_token: str) -> None:
        digest = refresh_digest(refresh_token)
        async with self._sessions() as db:
            await db.execute(
                update(AuthSession).where(AuthSession.refresh_digest == digest).values(revoked=True)
            )
            await db.commit()

    async def list_sessions(self, user_id: str) -> list[AuthSession]:
        async with self._sessions() as db:
            now = datetime.now(timezone.utc)
            rows = (
                await db.execute(
                    select(AuthSession).where(
                        AuthSession.user_id == user_id, AuthSession.revoked.is_(False)
                    )
                )
            ).scalars().all()
            return [s for s in rows if _aware(s.expires_at) > now]

    async def revoke_session(self, user_id: str, session_id: str) -> bool:
        async with self._sessions() as db:
            res = await db.execute(
                update(AuthSession)
                .where(AuthSession.id == session_id, AuthSession.user_id == user_id)
                .values(revoked=True)
            )
            await db.commit()
            return res.rowcount > 0

    # --- profile ---------------------------------------------------------------------

    async def update_profile(
        self, user_id: str, *, display_name: str | None = None, avatar_color: str | None = None,
        theme: str | None = None, language: str | None = None,
    ) -> User:
        async with self._sessions() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            if display_name is not None and display_name.strip():
                user.display_name = display_name.strip()[:120]
            if avatar_color is not None:
                user.avatar_color = avatar_color[:16]
            if theme in ("system", "dark", "light"):
                user.theme = theme
            if language in ("auto", "hi", "hinglish", "en"):
                user.language = language
            await db.commit()
            return user

    async def change_password(self, user_id: str, *, current: str, new: str) -> None:
        if len(new) < 8:
            raise AuthError("New password must be at least 8 characters.")
        async with self._sessions() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            if not verify_password(current, user.password_hash):
                raise AuthError("Current password is wrong.")
            user.password_hash = hash_password(new)
            # changing the password kills every OTHER device (this one re-logs)
            await db.execute(
                update(AuthSession).where(AuthSession.user_id == user_id).values(revoked=True)
            )
            await db.commit()

    # --- admin console (owner-only, Phase 8) ---------------------------------------

    async def admin_list_users(self) -> list[dict]:
        """Every account with its live-session count — the owner console table."""
        now = datetime.now(timezone.utc)
        async with self._sessions() as db:
            users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
            sessions = (await db.execute(
                select(AuthSession).where(AuthSession.revoked.is_(False))
            )).scalars().all()
            live: dict[str, int] = {}
            for s in sessions:
                if _aware(s.expires_at) > now:
                    live[s.user_id] = live.get(s.user_id, 0) + 1
            return [
                {
                    "id": u.id, "username": u.username, "display_name": u.display_name,
                    "email": u.email, "role": u.role, "theme": u.theme, "language": u.language,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "live_sessions": live.get(u.id, 0),
                }
                for u in users
            ]

    async def admin_reset_password(self, user_id: str, new_password: str) -> bool:
        """Owner sets a user's password directly; every session of that user dies."""
        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        async with self._sessions() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                return False
            user.password_hash = hash_password(new_password)
            await db.execute(
                update(AuthSession).where(AuthSession.user_id == user_id).values(revoked=True)
            )
            await db.commit()
            logger.info("admin reset password for %s (sessions revoked)", user.username)
            return True

    async def admin_revoke_sessions(self, user_id: str) -> int:
        async with self._sessions() as db:
            res = await db.execute(
                update(AuthSession).where(AuthSession.user_id == user_id).values(revoked=True)
            )
            await db.commit()
            return res.rowcount or 0

    async def admin_delete_user(self, user_id: str) -> None:
        """Delete an account + its sessions. The LAST owner is immortal —
        deleting them would brick the machine's entry door (no signup no entry)."""
        async with self._sessions() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                raise LookupError("User not found.")
            if user.role == "owner":
                owners = (await db.execute(
                    select(func.count()).select_from(User).where(User.role == "owner")
                )).scalar_one()
                if owners <= 1:
                    raise PermissionError(
                        "The last owner can't be deleted — make another owner first."
                    )
            await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
            await db.delete(user)
            await db.commit()
            self._count_cache = None  # keep the middleware lock fast-path honest
            logger.info("admin deleted user %s", user.username)
