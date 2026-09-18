"""Auth routes — register, login, refresh (rotating), logout, profile,
devices, password change. Cookie contract:

  vednix_rt    httpOnly · SameSite=Lax · Path=/api/auth   (refresh credential)
  vednix_csrf  readable by the SPA · mirrored back as X-CSRF-Token on
               cookie-bearing calls (double-submit CSRF defense)

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


def _set_session_cookies(response: Response, tokens: IssuedTokens, *, remember: bool) -> None:
    max_age = (30 * 24 * 3600) if remember else (12 * 3600)
    response.set_cookie(
        RT_COOKIE, tokens.refresh_token, max_age=max_age, httponly=True,
        samesite="lax", path="/api/auth",
    )
    response.set_cookie(
        CSRF_COOKIE, new_csrf_token(), max_age=max_age, httponly=False,
        samesite="lax", path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(RT_COOKIE, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _rt_cookie(request: Request) -> str:
    token = request.cookies.get(RT_COOKIE, "")
    if not token:
        raise HTTPException(status_code=401, detail="No session — sign in.")
    return token


def _token_payload(user, tokens: IssuedTokens) -> dict:
    return {
        "access_token": tokens.access_token,
        "expires_in": tokens.access_expires_in,
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
    _set_session_cookies(response, tokens, remember=True)
    logger.info("session opened after register (user=%s)", user.username)
    return _token_payload(user, tokens)


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
    _set_session_cookies(response, tokens, remember=body.remember)
    return _token_payload(user, tokens)


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
    _set_session_cookies(response, tokens, remember=body.remember)
    return _token_payload(user, tokens)


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
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = await users.get_user_by_session(tokens.session_id)
    if user is None:
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Account not found.")
    _set_session_cookies(response, tokens, remember=True)  # sliding renewal
    return _token_payload(user, tokens)


@router.post("/logout")
async def logout(request: Request, response: Response,
                 users: UserService = Depends(get_users)):
    require_csrf(request)
    rt = request.cookies.get(RT_COOKIE, "")
    if rt:
        await users.logout(refresh_token=rt)
    _clear_session_cookies(response)
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
    _clear_session_cookies(response)


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
