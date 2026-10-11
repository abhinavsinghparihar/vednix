"""Session tokens — HS256 JWT access tokens + opaque refresh tokens.

Deliberately stdlib (hmac/hashlib): HS256 JWT is a 30-line construction when
you control both issuer and audience (we do — same process). Pulling a whole
JWT library for one algorithm is how dependency rot starts.

Security contract:
  - Access token  : short-lived (20 min), signed, stateless. Claims: sub
    (user id), username, role, exp/iat, type="access", sid (the refresh
    session it was minted from — see SessionMiddleware's revocation check).
  - Refresh token : 48 random bytes, NEVER signed. Only its SHA-256 digest is
    stored (auth_sessions table) — a db leak can't mint sessions. Rotation on
    every use; a reused digest ⇒ theft ⇒ whole session chain is revoked.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import secrets as _secrets


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


class TokenError(ValueError):
    pass


def issue_access_token(
    secret: bytes, *, user_id: str, username: str, role: str, ttl_seconds: int,
    session_id: str | None = None,
) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims: dict[str, object] = {
        "sub": user_id, "username": username, "role": role,
        "iat": now, "exp": now + ttl_seconds, "type": "access",
        # jti: every issuance unique even inside the same second (enables
        # rotation assertions now and token-blacklisting later if needed)
        "jti": _secrets.token_hex(8),
    }
    if session_id:
        # sid binds the access token to its refresh session so logout and
        # admin "revoke-sessions" can be enforced instead of merely advised.
        claims["sid"] = session_id
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def verify_access_token(secret: bytes, token: str) -> dict:
    """Return claims or raise TokenError.

    Hardened verification contract:
      * exactly three segments, valid base64url in each;
      * the signature is checked BEFORE any claim is trusted (constant time);
      * the JOSE header must be exactly ``{"alg":"HS256","typ":"JWT"}`` — an
        unpinned header is how ``alg:none`` and RS256-confusion attacks start;
      * required claims are present and well-typed (sub/username/role/sid);
      * ``exp`` must be in the future and ``iat`` must not be (60s clock skew
        tolerated so a slightly-fast issuer can't mint eternal tokens).
    """
    try:
        header, payload, sig = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    expected = hmac.new(secret, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _b64url_decode(sig)
    except Exception as exc:
        raise TokenError("bad signature encoding") from exc
    if not hmac.compare_digest(expected, provided):
        raise TokenError("signature mismatch")
    try:
        header_claims = json.loads(_b64url_decode(header))
        claims = json.loads(_b64url_decode(payload))
    except Exception as exc:
        raise TokenError("malformed token") from exc
    if not isinstance(claims, dict) or header_claims != {"alg": "HS256", "typ": "JWT"}:
        raise TokenError("unsupported token header")
    if claims.get("type") != "access":
        raise TokenError("wrong token type")
    try:
        expires = int(claims.get("exp", 0))
        issued = int(claims.get("iat", 0))
    except (TypeError, ValueError) as exc:
        raise TokenError("invalid time claims") from exc
    now = int(time.time())
    if expires <= now:
        raise TokenError("token expired")
    if issued > now + 60:
        raise TokenError("token issued in the future")
    if not claims.get("sub") or not claims.get("username") or not claims.get("role"):
        raise TokenError("required claims missing")
    if not claims.get("sid"):
        # Tokens minted before session binding carry no sid: reject them so a
        # stale token can never outlive the revocation features below.
        raise TokenError("session claim missing")
    return claims


def new_refresh_token() -> str:
    """The cookie value the client holds. 48 bytes ⇒ 384 bits of entropy."""
    return _b64url(_secrets.token_bytes(48))


def refresh_digest(token: str) -> str:
    """What we actually store. Lookup key + theft detector in one."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_csrf_token() -> str:
    return _secrets.token_hex(16)


def hash_password(password: str, *, iterations: int = 600_000) -> str:
    """PBKDF2-HMAC-SHA256 — stdlib, memory-tunable, right-sized for a local
    app. 600k iterations is the OWASP Password Storage Cheat Sheet figure for
    PBKDF2-HMAC-SHA256. Format: pbkdf2$iters$salt_hex$hash_hex (self-describing,
    so hashes written at an older iteration count still verify)."""
    salt = _secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False
