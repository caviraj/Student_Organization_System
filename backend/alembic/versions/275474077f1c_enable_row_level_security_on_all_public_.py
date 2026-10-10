"""enable row level security on all public tables

Supabase publishes the `public` schema over its own REST API. Our FastAPI backend connects as the
table owner, so it is unaffected by RLS; the anonymous/authenticated roles Supabase hands out are
not - and with RLS on and NO policies, they can read nothing. Without this, any visitor holding
the publishable key could read every member, order and payment straight from that API.

Deliberately no policies: the API is the only door into this data.

Deliberately not FORCE ROW LEVEL SECURITY: the backend IS the table owner, and forcing RLS with no
policies would lock the backend out of its own tables as well.

The loop is the point - a table added by a later migration is covered when this runs again on a
fresh database, and the rule in AGENTS.md ("every new table migration must also ENABLE ROW LEVEL
SECURITY") is checked by `scripts/check_db.py` and by the test suite.

Revision ID: 275474077f1c
Revises: 1c897da66198
Create Date: 2026-10-10 11:40:02.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "275474077f1c"
down_revision: Union[str, Sequence[str], None] = "1c897da66198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# alembic_version is excluded: it holds one revision id, is Alembic's own bookkeeping, and is
# never exposed through the Supabase API.
_TABLES = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"


def _loop(action: str) -> str:
    return f"""
DO $$
DECLARE t record;
BEGIN
    FOR t IN {_TABLES} LOOP
        EXECUTE format('ALTER TABLE public.%I {action}', t.tablename);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # RLS is a Postgres feature; SQLite (local dev) has no equivalent
    op.execute(_loop("ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_loop("DISABLE ROW LEVEL SECURITY"))
