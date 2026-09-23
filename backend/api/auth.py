"""Auth routes — register, login, refresh (rotating), logout, profile,
devices, password change. Cookie contract:

  vednix_rt    httpOnly · Lax locally / None+Secure over HTTPS · Path=/api/auth
               (refresh credential)
  vednix_csrf  readable locally; cross-origin SPAs bootstrap it from /csrf
               and mirror it in X-CSRF-Token (double-submit CSRF defense)

Access tokens never touch cookies or storage: they live in SPA memory and
ride the Authorization header — XSS-persistent-token and CSRF classes are
both designed out, not patched over.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api.deps import current_user, get_auth_limiter, get_users
from api.schemas import (
    ChangePasswordIn,
    LoginIn,
    EmailOTPRequestIn,
    EmailOTPVerifyIn,
    ProfileUpdateIn,
    RegisterIn,
    SessionOut,
    UserOut,
)
from core.logging import get_logger
from core.session import CSRF_COOKIE, require_csrf
from core.tokens import new_csrf_token
from services.users import AuthError, IssuedTokens, UserService

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])

RT_COOKIE = "vednix_rt"


@router.get("/csrf")
async def csrf_bootstrap(request: Request, response: Response) -> dict:
    """Expose the non-authenticating CSRF nonce to the configured SPA origin.

    Third-party frontends (Vercel → Render) cannot read a cookie scoped to the
    API host, so the SPA bootstraps this nonce via credentialed CORS and keeps
    it in memory. The refresh token itself remains httpOnly and is never read.
    """
    token = request.cookies.get(CSRF_COOKIE, "")
    if not token or len(token) > 128:
        token = new_csrf_token()
        secure, same_site = _cookie_policy(request)
        response.set_cookie(
            CSRF_COOKIE, token, max_age=30 * 24 * 3600, httponly=False,
            secure=secure, samesite=same_site, path="/",
        )
    return {"csrf_token": token}


def _user_out(u) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, display_name=u.display_name, email=u.email,
        role=u.role, avatar_color=u.avatar_color, theme=u.theme, language=u.language,
        created_at=u.created_at,
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "local"


async def _throttle(request: Request, bucket: str) -> None:
    """Auth endpoints get their OWN 10/min bucket — the global limiter is
    far too permissive for credential paths (brute-force surface)."""
    allowed = await get_auth_limiter(request).allow(f"{bucket}:{_client_ip(request)}")
    if not allowed:
        raise HTTPException(status_code=429, detail="Slow down — too many attempts.")


def _cookie_policy(request: Request) -> tuple[bool, str]:
    """Use cross-site cookie attributes for HTTPS deployments, retain local Lax."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    origin = request.headers.get("origin", "").lower()
    secure = request.url.scheme == "https" or forwarded_proto == "https" or origin.startswith("https://")
    return secure, "none" if secure else "lax"


def _set_session_cookies(
    response: Response, tokens: IssuedTokens, *, remember: bool, request: Request,
) -> str:
    max_age = (30 * 24 * 3600) if remember else (12 * 3600)
    secure, same_site = _cookie_policy(request)
    csrf_token = new_csrf_token()
    response.set_cookie(
        RT_COOKIE, tokens.refresh_token, max_age=max_age, httponly=True,
        secure=secure, samesite=same_site, path="/api/auth",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False,
        secure=secure, samesite=same_site, path="/",
    )
    return csrf_token


def _clear_session_cookies(response: Response, request: Request) -> None:
    secure, same_site = _cookie_policy(request)
    response.delete_cookie(RT_COOKIE, path="/api/auth", secure=secure, samesite=same_site)
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite=same_site)


def _rt_cookie(request: Request) -> str:
    token = request.cookies.get(RT_COOKIE, "")
    if not token:
        raise HTTPException(status_code=401, detail="No session — sign in.")
    return token


def _token_payload(user, tokens: IssuedTokens, csrf_token: str) -> dict:
    return {
        "access_token": tokens.access_token,
        "expires_in": tokens.access_expires_in,
        "csrf_token": csrf_token,
        "user": _user_out(user).model_dump(mode="json"),
    }


# --- register / login ---------------------------------------------------------

@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request, response: Response,
                   users: UserService = Depends(get_users)):
    await _throttle(request, "register")
    try:
        user = await users.register(
            username=body.username, password=body.password,
            display_name=body.display_name, email=body.email, ip=_client_ip(request),
        )
    except AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # register logs you straight in — one less hop on a local app
    tokens = await users.issue_session_for(user, remember=True, device_label="This device")
    csrf_token = _set_session_cookies(response, tokens, remember=True, request=request)
    logger.info("session opened after register (user=%s)", user.username)
    return _token_payload(user, tokens, csrf_token)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response,
                users: UserService = Depends(get_users)):
    await _throttle(request, "login")
    try:
        user, tokens = await users.login(
            username=body.username, password=body.password, remember=body.remember,
            device_label=body.device_label or _ua_label(request), ip=_client_ip(request),
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    csrf_token = _set_session_cookies(response, tokens, remember=body.remember, request=request)
    return _token_payload(user, tokens, csrf_token)


@router.post("/email/request")
async def request_email_otp(body: EmailOTPRequestIn, request: Request, users: UserService = Depends(get_users)):
    await _throttle(request, "email-otp")
    settings = request.app.state.settings
    try:
        await users.request_email_otp(body.email, settings=settings, ip=_client_ip(request))
    except AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "message": "If this email is registered, a verification code has been sent."}


@router.post("/email/verify")
async def verify_email_otp(body: EmailOTPVerifyIn, request: Request, response: Response, users: UserService = Depends(get_users)):
    await _throttle(request, "email-otp-verify")
    try:
        user = await users.verify_email_otp(body.email, body.code)
        tokens = await users.issue_session_for(user, remember=body.remember, device_label=_ua_label(request))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    csrf_token = _set_session_cookies(response, tokens, remember=body.remember, request=request)
    return _token_payload(user, tokens, csrf_token)


def _ua_label(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    for hint, label in (("Edg", "Edge"), ("Firefox", "Firefox"), ("Chrome", "Chrome"),
                        ("Safari", "Safari")):
        if hint in ua:
            os_hint = "Windows" if "Windows" in ua else "macOS" if "Mac OS" in ua else \
                      "Linux" if "Linux" in ua else "device"
            return f"{label} on {os_hint}"
    return "This device"


# --- refresh / logout -------------------------------------------------------------

@router.post("/refresh")
async def refresh(request: Request, response: Response,
                  users: UserService = Depends(get_users)):
    await _throttle(request, "refresh")
    require_csrf(request)
    rt = _rt_cookie(request)
    try:
        tokens = await users.refresh(refresh_token=rt, device_label=_ua_label(request))
    except AuthError as exc:
        _clear_session_cookies(response, request)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = await users.get_user_by_session(tokens.session_id)
    if user is None:
        _clear_session_cookies(response, request)
        raise HTTPException(status_code=401, detail="Account not found.")
    csrf_token = _set_session_cookies(response, tokens, remember=True, request=request)  # sliding renewal
    return _token_payload(user, tokens, csrf_token)


@router.post("/logout")
async def logout(request: Request, response: Response,
                 users: UserService = Depends(get_users)):
    require_csrf(request)
    rt = request.cookies.get(RT_COOKIE, "")
    if rt:
        await users.logout(refresh_token=rt)
    _clear_session_cookies(response, request)
    return {"ok": True}


# --- me / profile / devices --------------------------------------------------------

@router.get("/me", response_model=UserOut)
async def me(claims: dict = Depends(current_user), users: UserService = Depends(get_users)):
    user = await users.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return _user_out(user)


@router.patch("/me", response_model=UserOut)
async def update_me(body: ProfileUpdateIn, claims: dict = Depends(current_user),
                    users: UserService = Depends(get_users)):
    user = await users.update_profile(
        claims["sub"], display_name=body.display_name, avatar_color=body.avatar_color,
        theme=body.theme, language=body.language,
    )
    return _user_out(user)


@router.post("/me/password", status_code=204)
async def change_password(body: ChangePasswordIn, request: Request, response: Response,
                          claims: dict = Depends(current_user),
                          users: UserService = Depends(get_users)):
    try:
        await users.change_password(
            claims["sub"], current=body.current_password, new=body.new_password
        )
    except AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # every device was revoked — drop this browser's cookies too
    _clear_session_cookies(response, request)


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(request: Request, claims: dict = Depends(current_user),
                   users: UserService = Depends(get_users)):
    rt_digest = None
    rt = request.cookies.get(RT_COOKIE, "")
    from core.tokens import refresh_digest  # local: avoid import cost on hot paths
    if rt:
        rt_digest = refresh_digest(rt)
    rows = await users.list_sessions(claims["sub"])
    out = []
    for s in rows:
        out.append(SessionOut(
            id=s.id, device_label=s.device_label, remember=s.remember,
            current=(rt_digest == s.refresh_digest),
            last_seen_at=s.last_seen_at, created_at=s.created_at,
        ))
    return out


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke(session_id: str, claims: dict = Depends(current_user),
                 users: UserService = Depends(get_users)):
    ok = await users.revoke_session(claims["sub"], session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found.")
