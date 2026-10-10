"""Keeping the `permissions` / `roles` tables in step with app/core/permissions.py.

The catalog module is the source of truth: it is what `require_permission` validates route keys
against at import time. The tables are its copy - what the admin UI lists, what `roles` is joined
to. There is exactly one implementation of "load the module into the database", and the migration
that creates the tables and `scripts/seed.py` both call it, so the two can never disagree.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import CATALOG, ROLE_PERMISSIONS, ROLE_SPECS, SYSTEM_ROLES
from app.models import Permission, Role, RolePermission, SodRule

# (role_a, role_b) - whoever reads the books must not be whoever writes them. Seeded, and editable
# by a super admin afterwards, which is why the rule lives in a table rather than in this module.
SOD_PAIRS: tuple[tuple[str, str], ...] = (
    ("auditor", "treasurer"),
    ("auditor", "super_admin"),
    ("auditor", "admin"),
)


def sync_catalog(db: Session) -> None:
    """Upsert permissions and system roles. Idempotent - safe to run on every deploy.

    Existing rows are updated rather than replaced, so a role's `id` survives and the `user_roles`
    pointing at it keep pointing at it.
    """
    permissions: dict[str, Permission] = {row.key: row for row in db.scalars(select(Permission))}
    for spec in CATALOG:
        row = permissions.get(spec.key)
        if row is None:
            row = Permission(key=spec.key)
            db.add(row)
            permissions[spec.key] = row
        row.description = spec.description
        row.category = spec.category
        row.is_privileged = spec.is_privileged
    db.flush()

    roles: dict[str, Role] = {row.key: row for row in db.scalars(select(Role))}
    for spec in ROLE_SPECS:
        row = roles.get(spec.key)
        if row is None:
            row = Role(key=spec.key)
            db.add(row)
            roles[spec.key] = row
        row.name = spec.name
        row.description = spec.description
        row.is_system = True
        row.is_active = True
        row.is_privileged = bool(ROLE_PERMISSIONS[spec.key] & {p.key for p in CATALOG if p.is_privileged})
    db.flush()

    # Replace each system role's grants wholesale: the module is the source of truth for these, so
    # anything extra on a system role is drift, not a local edit worth preserving.
    for key in SYSTEM_ROLES:
        role = roles[key]
        wanted = {permissions[perm].id for perm in ROLE_PERMISSIONS[key]}
        have = {
            link.permission_id for link in db.scalars(select(RolePermission).where(RolePermission.role_id == role.id))
        }
        for missing in wanted - have:
            db.add(RolePermission(role_id=role.id, permission_id=missing))
        for extra in have - wanted:
            db.delete(db.get(RolePermission, (role.id, extra)))

    for a, b in SOD_PAIRS:
        exists = db.scalar(select(SodRule).where(SodRule.role_a_id == roles[a].id, SodRule.role_b_id == roles[b].id))
        if exists is None:
            db.add(
                SodRule(
                    role_a_id=roles[a].id,
                    role_b_id=roles[b].id,
                    description=f"{roles[a].name} and {roles[b].name} must not be held by the same person.",
                )
            )
    db.flush()
