"""Admin console (Phase 8) — owner-only control over every account on this
machine. The FIRST registered account is the owner; everyone else answers
to them. A member gets 403, an anonymous request never makes it past the
session lock (401).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import current_user, get_users
from services.users import UserService

router = APIRouter(tags=["admin"])


def require_owner(claims: dict = Depends(current_user)) -> dict:
    """One gate, every admin route: the JWT itself carries the role."""
    if claims.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Owner access required.")
    return claims


class AdminPasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)


@router.get("/users")
async def list_users(_: dict = Depends(require_owner), users: UserService = Depends(get_users)):
    return {"users": await users.admin_list_users()}


@router.post("/users/{user_id}/password")
async def reset_password(user_id: str, body: AdminPasswordIn,
                         _: dict = Depends(require_owner),
                         users: UserService = Depends(get_users)):
    try:
        ok = await users.admin_reset_password(user_id, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True}


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_sessions(user_id: str, _: dict = Depends(require_owner),
                          users: UserService = Depends(get_users)):
    return {"revoked": await users.admin_revoke_sessions(user_id)}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, claims: dict = Depends(require_owner),
                      users: UserService = Depends(get_users)):
    if claims["sub"] == user_id:
        raise HTTPException(status_code=400,
                            detail="You can't delete yourself — another owner must.")
    try:
        await users.admin_delete_user(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}
