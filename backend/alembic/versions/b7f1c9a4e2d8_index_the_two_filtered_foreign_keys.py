"""index the two foreign keys the API actually filters on

Phase 7 reviewed every foreign key in the `public` schema against `pg_indexes`, asking which ones
have a supporting index. Twenty do not, and most of them should not: `created_by`,
`reviewed_by`, `closed_by` and their neighbours are display-only, joined as
`outerjoin(User, X.col == User.id)`, which uses the primary key on `users` and never an index on
the referencing column. Adding twenty indexes "because they are foreign keys" would cost write
amplification on every insert and buy nothing.

Two of the twenty are filtered by the API, so they are the two worth an index:

  * `tasks.event_id` - `GET /tasks?event_id=` filters on it, and the board's visibility scope
    clause is `Task.event_id == <the viewer's ticket's event>`. Without an index this is a
    sequential scan of the whole task table for every viewer who is not staff.
  * `fundraisers.owner_id` - `GET /fundraisers?owner_id=` filters on it, for the "my fundraisers"
    view.

Both are invisible at the seeded sizes (17 tasks, 4 fundraisers) - EXPLAIN still chooses a seq
scan, correctly - and both are the difference between one index lookup and a growing table scan
once a semester of data is in. The remaining eighteen are deliberately left alone.

Revision ID: b7f1c9a4e2d8
Revises: ecd63b2a99ac
Create Date: 2026-10-10 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f1c9a4e2d8"
down_revision: Union[str, Sequence[str], None] = "ecd63b2a99ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_tasks_event_id", "tasks", ["event_id"])
    op.create_index("ix_fundraisers_owner_id", "fundraisers", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_fundraisers_owner_id", table_name="fundraisers")
    op.drop_index("ix_tasks_event_id", table_name="tasks")
