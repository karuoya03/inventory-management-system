"""Small helper for writing audit log entries."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Add an audit row to the session. Caller commits."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
        )
    )