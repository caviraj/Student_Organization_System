"""Permission checks - the one place a request is allowed or refused.

Where a user's permissions come from, in two parts:

* `users.role`, the legacy single role, still read directly. It is the primary global assignment:
  the column every phase-1 route already keys off, and the one `require_role` compared. Keeping it
  authoritative is what makes the move to permissions a provable no-op - the golden matrix in
  tests/fixtures/authz_golden.json has to show every cell unchanged, and it cannot if the refactor
  quietly re-derives everyone's access from a table nobody has filled in yet.
* `user_roles`, for everything the single column cannot express: a second role, a role scoped to one
  event, and a role with an end date. Rows count only while live (`revoked_at IS NULL` and inside
  `valid_from`/`valid_to`), so a term handover is a date, not a cleanup job.

`require_permission` replaces `require_role` route by route. It takes more than one key where a
route can be reached two ways - `events.manage_all` for an organizer's own event, `events.manage_own`
for the lead of that one event - and passes anyone holding *any* of them; requiring all of them
would make the narrower path unreachable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import AppError
from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLE_RANK_ORDER
from app.models import User

# A permission nobody in the ladder holds (events.manage_own is event_lead's alone) has no floor, so
# contract_check cannot compare it to a DESIGN.md Role cell. Derived here, where the catalog is.
PERMISSION_FLOOR: dict[str, str] = {}
for _role in ROLE_RANK_ORDER[1:]:
    for _key in ROLE_PERMISSIONS[_role]:
        PERMISSION_FLOOR.setdefault(_key, _role)
del _role, _key


def role_keys(user: User) -> frozenset[str]:
    """Every role the user holds right now: the primary column plus every live assignment, whether
    that assignment is global or scoped. For display - `effective_permissions` is what decides what a
    scoped role actually buys.

    No query of its own: `User.user_roles` is a lazy relationship, so the rows arrive with the
    session's identity map and a request that checks permissions six times still reads them once.
    """
    keys = {user.role} if user.role != "guest" else set()
    now = datetime.now(UTC)
    for row in user.user_roles:
        if row.revoked_at is None and row.valid_from <= now and (row.valid_to is None or row.valid_to > now):
            keys.add(row.role.key)
    return frozenset(keys)


def effective_permissions(db: Session, user: User, scope_id: UUID | None = None) -> frozenset[str]:
    """The permission keys this user holds, optionally for one scoped resource.

    A global assignment counts everywhere; a scoped one counts only on the resource it names, so an
    `event_lead` for the Spring Gala cannot edit the Autumn Ball. That is why this walks the rows
    itself rather than starting from `role_keys`: reading every live role and only *then* filtering
    by scope would hand a scoped role its permissions globally.

    `db` is unused today - the rows come from the loaded relationship - and is kept in the signature
    because resolving a scope from a route parameter is the caller's job, not this function's.
    """
    roles = {user.role} if user.role != "guest" else set()
    now = datetime.now(UTC)
    for row in user.user_roles:
        if row.revoked_at is not None or row.valid_from > now:
            continue
        if row.valid_to is not None and row.valid_to <= now:
            continue
        if row.scope_type == "global" or (scope_id is not None and row.scope_id == scope_id):
            roles.add(row.role.key)
    return frozenset(key for role in roles for key in ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(db: Session, user: User, key: str, scope_id: UUID | None = None) -> bool:
    return key in effective_permissions(db, user, scope_id)


def bump_authz_version(db: Session, user: User) -> None:
    """Call after any change to what a user may do. Their live tokens stop working on the next
    request instead of at expiry."""
    user.authz_version += 1
    db.flush()


def require_permission(*keys: str, scope: Callable[..., UUID | None] | None = None) -> Callable[..., User]:
    """Dependency factory: passes anyone holding ANY of `keys`.

    Keys are validated against app/core/permissions.py here, at import time. A typo is a crash when
    the app loads, not a 403 for a real user weeks later.
    """
    unknown = [key for key in keys if key not in PERMISSIONS]
    if unknown:
        raise RuntimeError(f"require_permission: unknown permission key(s) {unknown}")
    if not keys:
        raise RuntimeError("require_permission needs at least one key")

    def dependency(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        scope_id = scope(user, db) if scope is not None else None
        held = effective_permissions(db, user, scope_id)
        if not held & set(keys):
            raise AppError(
                403,
                "FORBIDDEN",
                f"Requires permission: {' or '.join(keys)}",
                {"your_role": user.role, "missing": sorted(keys)},
            )
        return user

    # Read by scripts/contract_check.py to compare the route's real floor against DESIGN.md §5.
    dependency.required_permissions = keys  # type: ignore[attr-defined]
    return dependency
