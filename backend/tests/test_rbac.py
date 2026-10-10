"""The permission engine: the catalog, its copy in the database, and who holds what.

Three things are pinned here, and each one is a way the RBAC refactor could rot without a test
noticing. The **catalog and the tables** must agree, or the admin UI shows a role a permission it
does not have. Every **new table** must keep RLS on, or Supabase's REST API publishes it. And the
**two sources of a user's roles** - the `users.role` column and the `user_roles` assignments - must
combine the way `app.core.authz` claims they do, including the window and the revocation.
"""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from sqlalchemy import func, select, text

from app.core.authz import effective_permissions, has_permission, require_permission, role_keys
from app.core.permissions import CATALOG, ROLE_PERMISSIONS, ROLE_SPECS
from app.core.routes import iter_api_routes
from app.main import app
from app.models import Permission, Role, RolePermission, SodRule, UserRole
from app.services.rbac import sync_catalog


@pytest.fixture
def roles(db) -> dict[str, Role]:
    return {row.key: row for row in db.scalars(select(Role))}


@pytest.fixture
def organizer(make_user):
    return make_user("organizer@ssa.org", role="organizer")


@pytest.fixture
def member(make_user):
    return make_user("member@ssa.org", role="member")


# --- 1. the module and its copy in the database -----------------------------------
def test_the_permission_table_is_the_catalog(db):
    """The migration runs `sync_catalog`, so the tables are what the module says they are."""
    rows = {row.key: row for row in db.scalars(select(Permission))}
    assert set(rows) == {p.key for p in CATALOG}
    for spec in CATALOG:
        row = rows[spec.key]
        assert (row.category, row.description, row.is_privileged) == (
            spec.category,
            spec.description,
            spec.is_privileged,
        )


def test_the_role_table_is_the_role_specs(db):
    rows = {row.key: row for row in db.scalars(select(Role))}
    assert set(rows) == {spec.key for spec in ROLE_SPECS}
    for spec in ROLE_SPECS:
        row = rows[spec.key]
        assert (row.name, row.description, row.is_system) == (spec.name, spec.description, True)


def test_every_role_grants_exactly_what_the_module_says(db, roles):
    """The join table, not the module: this is the copy that can silently drift."""
    for spec in ROLE_SPECS:
        granted = set(
            db.scalars(
                select(Permission.key)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == roles[spec.key].id)
            )
        )
        assert granted == ROLE_PERMISSIONS[spec.key], f"{spec.key} drifted from app/core/permissions.py"


def test_a_role_carrying_a_privileged_permission_is_flagged_as_one(db, roles):
    from app.core.permissions import PRIVILEGED_PERMISSIONS

    for spec in ROLE_SPECS:
        expected = bool(ROLE_PERMISSIONS[spec.key] & PRIVILEGED_PERMISSIONS)
        assert roles[spec.key].is_privileged is expected, spec.key


def test_sync_catalog_is_idempotent(db, roles):
    """It runs on every deploy, so a second run must change nothing - not the rows, and not the
    ids a `user_roles` row points at."""

    def snapshot() -> dict:
        return {
            "roles": {row.key: row.id for row in db.scalars(select(Role))},
            "permissions": {row.key: row.id for row in db.scalars(select(Permission))},
            "grants": {(link.role_id, link.permission_id) for link in db.scalars(select(RolePermission))},
        }

    before = snapshot()
    sync_catalog(db)
    db.commit()
    db.expire_all()

    assert snapshot() == before


def test_sync_catalog_prunes_a_grant_the_module_no_longer_makes(db, roles):
    """The module is the source of truth, so a grant on a *system* role that is not in the module is
    drift: a permission removed from a role has to actually come off it."""
    assert "audit.view" not in ROLE_PERMISSIONS["admin"], "pick a permission admin really does not hold"
    audit = db.scalar(select(Permission).where(Permission.key == "audit.view"))
    db.add(RolePermission(role_id=roles["admin"].id, permission_id=audit.id))
    db.commit()

    sync_catalog(db)
    db.commit()

    remaining = db.scalar(
        select(func.count())
        .select_from(RolePermission)
        .where(RolePermission.role_id == roles["admin"].id, RolePermission.permission_id == audit.id)
    )
    assert remaining == 0


def test_the_separation_of_duties_rules_are_seeded(db, roles):
    """Whoever reads the books must not also be whoever writes them."""
    pairs = {(row.role_a_id, row.role_b_id) for row in db.scalars(select(SodRule).order_by(SodRule.role_a_id))}
    assert (roles["auditor"].id, roles["treasurer"].id) in pairs
    assert (roles["auditor"].id, roles["super_admin"].id) in pairs
    assert all(row.description for row in db.scalars(select(SodRule)))


# --- 2. row level security --------------------------------------------------------
def test_every_new_table_keeps_its_door_shut(db):
    """Supabase publishes `public` over its own REST API; RLS-on-with-no-policies is the only thing
    keeping these tables off it."""
    rows = dict(
        db.execute(
            text(
                "select tablename, rowsecurity from pg_tables "
                "where schemaname = 'public' and tablename in "
                "('permissions', 'roles', 'role_permissions', 'user_roles', 'sod_rules')"
            )
        ).all()
    )
    assert rows == {
        "permissions": True,
        "roles": True,
        "role_permissions": True,
        "user_roles": True,
        "sod_rules": True,
    }


# --- 3. where a user's roles come from --------------------------------------------
def test_the_primary_column_alone_decides_the_ladder_role(db, organizer):
    assert role_keys(organizer) == {"organizer"}
    assert has_permission(db, organizer, "events.manage_all") is True
    assert has_permission(db, organizer, "roles.assign") is False


def test_a_guest_holds_no_role_at_all(db, make_user):
    """`guest` is not a role with no permissions, it is the absence of one - an unpaid registrant
    must not inherit anything from the column's default value."""
    guest = make_user("guest@ssa.org", role="guest")
    assert role_keys(guest) == frozenset()
    assert effective_permissions(db, guest) == frozenset()


def test_an_assignment_adds_a_role_the_column_cannot_express(db, member, roles):
    db.add(UserRole(user_id=member.id, role_id=roles["auditor"].id))
    db.commit()
    db.refresh(member)

    assert role_keys(member) == {"member", "auditor"}
    assert has_permission(db, member, "audit.view") is True
    assert has_permission(db, member, "finance.manage_entries") is False, "auditor reads, never writes"


def test_an_expired_or_revoked_assignment_stops_counting(db, member, roles):
    """A term handover is a date, not a cleanup job: the row stays for the audit trail."""
    now = datetime.now(UTC)
    expired = UserRole(
        user_id=member.id,
        role_id=roles["auditor"].id,
        valid_from=now - timedelta(days=30),
        valid_to=now - timedelta(seconds=1),
    )
    revoked = UserRole(
        user_id=member.id,
        role_id=roles["treasurer"].id,
        revoked_at=now,
        valid_from=now - timedelta(days=30),
    )
    db.add_all([expired, revoked])
    db.commit()
    db.refresh(member)

    assert role_keys(member) == {"member"}
    assert has_permission(db, member, "audit.view") is False
    assert has_permission(db, member, "finance.manage_entries") is False


def test_a_scoped_assignment_counts_only_on_its_own_resource(db, member, roles, organizer):
    from uuid import uuid4

    event_id = uuid4()
    db.add(UserRole(user_id=member.id, role_id=roles["event_lead"].id, scope_type="event", scope_id=event_id))
    db.commit()
    db.refresh(member)

    assert has_permission(db, member, "events.manage_own", event_id) is True
    assert has_permission(db, member, "events.manage_own", uuid4()) is False
    assert (
        has_permission(db, member, "events.manage_own") is False
    ), "a scoped role is not a global one - the unscoped answer must not include it"
    assert has_permission(db, member, "events.manage_all") is False, "own, not all - the ladder is untouched"
    # `role_keys` is the display answer and does list it, scoped or not.
    assert role_keys(member) == {"member", "event_lead"}
    # The global column is unaffected by a scoped row on someone else.
    assert has_permission(db, organizer, "events.manage_all", event_id) is True


# --- 4. the dependency factory ----------------------------------------------------
def test_an_unknown_permission_key_crashes_at_build_time():
    """A typo must be a crash when the module is imported, not a 403 for a real user weeks later."""
    with pytest.raises(RuntimeError, match="unknown permission key"):
        require_permission("evnts.manage_all")
    with pytest.raises(RuntimeError, match="at least one key"):
        require_permission()


# --- 5. the endpoints -------------------------------------------------------------
def test_my_permissions_are_mine(client, auth, login, organizer):
    response = client.get("/api/v1/auth/permissions", headers=auth(login(organizer.email)))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "organizer"
    assert body["roles"] == ["organizer"]
    assert set(body["permissions"]) == ROLE_PERMISSIONS["organizer"]
    assert "roles.assign" not in body["permissions"], "the frontend hides the button on this"


def test_my_permissions_lists_an_assignment_too(client, auth, login, db, member, roles):
    db.add(UserRole(user_id=member.id, role_id=roles["auditor"].id))
    db.commit()

    body = client.get("/api/v1/auth/permissions", headers=auth(login(member.email))).json()
    assert body["role"] == "member", "the column still reports the ladder role"
    assert body["roles"] == ["auditor", "member"]
    assert "audit.view" in body["permissions"] and "members.view" in body["permissions"]


def test_my_permissions_needs_a_token(client):
    assert client.get("/api/v1/auth/permissions").status_code == 401


def test_the_catalog_is_admin_only(client, auth, login, member, make_user):
    assert client.get("/api/v1/admin/permissions", headers=auth(login(member.email))).status_code == 403

    admin = make_user("admin@ssa.org", role="admin")
    response = client.get("/api/v1/admin/permissions", headers=auth(login(admin.email)))
    assert response.status_code == 200, response.text
    rows = {row["key"]: row for row in response.json()}
    assert set(rows) == {p.key for p in CATALOG}
    assert rows["roles.assign"]["is_privileged"] is True
    assert rows["members.view"]["is_privileged"] is False


def test_the_matrix_covers_every_role_and_every_permission(client, auth, login, make_user):
    admin = make_user("admin@ssa.org", role="admin")
    body = client.get("/api/v1/admin/rbac/matrix", headers=auth(login(admin.email))).json()

    assert {row["key"] for row in body["permissions"]} == {p.key for p in CATALOG}
    roles = {row["key"]: row for row in body["roles"]}
    assert set(roles) == {spec.key for spec in ROLE_SPECS}
    for spec in ROLE_SPECS:
        assert set(roles[spec.key]["permissions"]) == ROLE_PERMISSIONS[spec.key]

    # The ladder is what makes the refactor a no-op: each rung holds everything below it.
    ladder = ("member", "volunteer", "organizer", "treasurer", "admin", "super_admin")
    for lower, higher in pairwise(ladder):
        assert set(roles[lower]["permissions"]) < set(roles[higher]["permissions"]), f"{lower} not nested in {higher}"

    # `auditor` and `event_lead` sit outside the ladder on purpose. An auditor reads the books and
    # must never inherit the treasurer's writes, or the role is worse than useless. An event lead
    # inherits volunteer - not organizer - which is exactly why `events.manage_own` exists beside
    # `events.manage_all`.
    writes = {"finance.manage_entries", "finance.reverse", "expenses.review", "expenses.reimburse"}
    assert not set(roles["auditor"]["permissions"]) & writes
    assert roles["auditor"]["inherits"] is None and "audit.view" in roles["auditor"]["permissions"]
    assert roles["event_lead"]["inherits"] == "volunteer"
    assert "events.manage_own" in roles["event_lead"]["permissions"]
    assert "events.manage_all" not in roles["event_lead"]["permissions"]


def test_the_matrix_is_admin_only(client, auth, login, member):
    assert client.get("/api/v1/admin/rbac/matrix", headers=auth(login(member.email))).status_code == 403


# --- 6. the generated doc ---------------------------------------------------------
def test_the_rbac_doc_is_current():
    """`docs/RBAC.md` is generated from the catalog and the app. A new permission, a new role or a
    rerouted guard that nobody re-rendered fails here rather than reaching a reader who trusts it."""
    from scripts.generate_rbac_doc import DEST, render

    assert DEST.exists(), "docs/RBAC.md is missing - run `python scripts/generate_rbac_doc.py`"
    assert (
        DEST.read_text(encoding="utf-8") == render()
    ), "docs/RBAC.md is stale - run `python scripts/generate_rbac_doc.py`"


def test_the_route_map_in_the_doc_names_every_guard():
    """The doc's route map is the answer to "I got a 403, what do I need?". It is only worth reading
    if every route's row is the keys its dependency actually declares."""
    from scripts.generate_rbac_doc import guard_keys, render

    text = render()
    for path, route in iter_api_routes(app):
        if not guard_keys(route):
            continue
        assert f"| `{path}` |" in text, f"{path} is missing from the route map"
