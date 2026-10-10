"""m2 phase 2: permissions, roles, role_permissions, user_roles, sod_rules

Adds `users.authz_version` and the five tables behind permission-based access control.

The catalog and the system roles are loaded from app/core/permissions.py through
`app.services.rbac.sync_catalog`, the same function `scripts/seed.py` calls. The module is the source
of truth - `require_permission` validates route keys against it at import - so seeding the tables
from anything else would be a second copy to drift. The trade-off is that a migration replaying on a
fresh database seeds whatever the catalog says today rather than on the day this was written; for
reference data that is what you want, and no permission is ever *removed* by a replay.

No backfill of `user_roles` from `users.role`. The column stays authoritative as the primary global
assignment and is read directly by app/core/authz.py; copying it into `user_roles` would create two
stores of one fact to keep in step. See docs/RBAC.md.

RLS is enabled here explicitly rather than left to 275474077f1c, which loops over the tables that
exist when it runs - these five do not exist yet at that point.

Revision ID: 0c4d5b7e91a3
Revises: b7f1c9a4e2d8
Create Date: 2026-10-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = "0c4d5b7e91a3"
down_revision: Union[str, Sequence[str], None] = "b7f1c9a4e2d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ("permissions", "roles", "role_permissions", "user_roles", "sod_rules")

# length matches the longest value ("fundraiser"), as SQLAlchemy infers it for `_enum`; a different
# length here would make `alembic check` report a phantom diff forever.
SCOPE_TYPES = sa.Enum(
    "global", "event", "fundraiser", "committee", name="user_role_scope", native_enum=False, length=10
)


def upgrade() -> None:
    op.add_column("users", sa.Column("authz_version", sa.Integer(), nullable=False, server_default=sa.text("1")))

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("is_privileged", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_permissions_key", "permissions", ["key"], unique=True)
    op.create_index("ix_permissions_category", "permissions", ["category"])

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_privileged", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_roles_key", "roles", ["key"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Uuid(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("scope_type", SCOPE_TYPES, nullable=False, server_default=sa.text("'global'")),
        sa.Column("scope_id", sa.Uuid()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("reason", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("approval_request_id", sa.Uuid()),
        sa.CheckConstraint("scope_type = 'global' OR scope_id IS NOT NULL", name="ck_user_roles_scoped_needs_id"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_user_roles_window_ordered"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_scope_id", "user_roles", ["scope_id"])
    op.create_index("ix_user_roles_valid_to", "user_roles", ["valid_to"])
    op.create_index("ix_user_roles_user_open", "user_roles", ["user_id", "revoked_at"])
    op.create_index("ix_user_roles_role_open", "user_roles", ["role_id", "revoked_at"])

    op.create_table(
        "sod_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("role_a_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_b_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("role_a_id", "role_b_id", name="uq_sod_rules_pair"),
    )

    if op.get_bind().dialect.name == "postgresql":
        # RLS on, no policies: the Supabase REST door is shut, the backend (table owner) is not.
        for table in NEW_TABLES:
            op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')

    # Imported here, not at module level: alembic loads every revision file when it builds the
    # version graph, including during `alembic downgrade`, and app code must not be a hard import.
    from app.services.rbac import sync_catalog

    with Session(bind=op.get_bind()) as db:
        sync_catalog(db)
        db.commit()


def downgrade() -> None:
    op.drop_table("sod_rules")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_column("users", "authz_version")
