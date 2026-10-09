"""User administration — listing and editing staff accounts (admin only)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select

from app.deps import DbSession, require_roles
from app.models import Role, User
from app.schemas import UserPublic, UserUpdate
from app.services import audit

router = APIRouter(prefix="/api/users", tags=["Users"])

AdminOnly = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("", response_model=list[UserPublic], summary="List staff accounts")
def list_users(
    db: DbSession,
    _admin: AdminOnly,
    q: str | None = Query(default=None, max_length=120),
    role: Role | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[User]:
    stmt = select(User).order_by(User.full_name).limit(limit).offset(offset)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.full_name.like(like),
                User.username.like(like),
                User.email.like(like),
            )
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))
    return list(db.scalars(stmt))


@router.patch("/{user_id}", response_model=UserPublic, summary="Update a staff account")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: DbSession,
    admin: AdminOnly,
    request: Request,
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Don't let an admin lock the whole team out of the admin panel.
    if user.id == admin.id:
        if payload.is_active is False:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
        if payload.role is not None and payload.role != Role.ADMIN:
            raise HTTPException(status_code=400, detail="You cannot change your own role.")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    # Refuse to demote the last active administrator.
    if user.role == Role.ADMIN and updates.get("role") not in (None, Role.ADMIN):
        remaining = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.ADMIN, User.is_active.is_(True))
        ) or 0
        if remaining <= 1:
            raise HTTPException(
                status_code=409, detail="At least one active administrator must remain."
            )

    for field, value in updates.items():
        setattr(user, field, value)

    audit.record(
        db,
        user_id=admin.id,
        action="update",
        entity="user",
        entity_id=user.id,
        details=",".join(updates.keys()),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return user