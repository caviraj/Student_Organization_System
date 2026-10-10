"""The permission catalog and the system roles - one module, so a typo cannot reach production.

Every permission key in the codebase is a string constant declared here, and `require_permission`
validates the key against this module *at import time*. A route declaring `"evnts.manage_all"` is a
RuntimeError when the app is imported, not a silent 403 for real users three weeks later. That is
the whole reason the catalog is a module and not a database-only concern: the database copy is for
the admin UI, this copy is what the code is checked against.

The system roles are deliberately **nested** - member c⊂ volunteer ⊂ organizer ⊂ treasurer ⊂ admin ⊂
super_admin. That is what lets the M2-P2 refactor be a provable no-op for every existing user: each
legacy `require_role("organizer")` becomes `require_permission(<something organizer and above
hold>)`, and the golden matrix in tests/fixtures/authz_golden.json is what proves it.

`secretary`, `event_lead` and `auditor` sit outside the ladder on purpose. An auditor must not
inherit treasurer's write permissions, or the role is worse than useless.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    key: str
    category: str
    description: str
    is_privileged: bool = False


def _p(key: str, category: str, description: str, is_privileged: bool = False) -> Permission:
    return Permission(key, category, description, is_privileged)


# `is_privileged` means "holding this is a big deal": granting any role that contains one of these
# goes through a maker-checker approval (M2-P2 Step 2), and the permissions in
# MFA_ENFORCED_PERMISSIONS force enrolment (Step 3).
CATALOG: tuple[Permission, ...] = (
    # --- identity and access -----------------------------------------------------
    _p("users.view", "identity", "See the member directory", True),
    _p("users.lookup", "identity", "Search users to assign work to"),
    _p("users.manage", "identity", "Edit member records", True),
    _p("users.invite", "identity", "Invite someone into a role", True),
    _p("users.suspend", "identity", "Suspend, deactivate, reactivate or unlock an account", True),
    _p("roles.view", "identity", "See the role and permission catalog"),
    _p("roles.manage", "identity", "Create, edit and delete custom roles", True),
    _p("roles.assign", "identity", "Give and revoke roles", True),
    _p("roles.assign_privileged", "identity", "Give and revoke roles carrying privileged permissions", True),
    _p("system.settings", "identity", "Change platform-wide settings", True),
    # --- membership --------------------------------------------------------------
    _p("members.view", "membership", "See your own membership card", False),
    _p("members.manage", "membership", "See every membership and the renewals-due list", True),
    _p("members.verify", "membership", "Verify a member at the door by code or name/email"),
    _p("plans.manage", "membership", "Create and edit membership plans", True),
    # --- events and tickets ------------------------------------------------------
    _p("events.view_drafts", "events", "See unpublished events"),
    _p("events.manage_all", "events", "Create and edit any event and its ticket types"),
    _p("events.manage_own", "events", "Create and edit events you lead"),
    _p("tickets.checkin", "events", "Scan a ticket at the door"),
    _p("attendees.view", "events", "See who is coming to an event"),
    _p("event_reports.view", "events", "See an event's sales and attendance report"),
    # --- announcements -----------------------------------------------------------
    _p("announcements.post", "announcements", "Publish an announcement"),
    _p("announcements.manage", "announcements", "Edit an announcement and read its revision history"),
    _p("announcements.view_all", "announcements", "See announcements addressed to every audience"),
    _p("announcements.view_deliveries", "announcements", "See per-recipient delivery records", True),
    # --- merchandise -------------------------------------------------------------
    _p("products.manage", "merch", "Create, edit and retire products, variants and stock", True),
    _p("merch_orders.manage", "merch", "Work the order board and adjust any order", True),
    _p("stock.adjust", "merch", "Adjust stock and read stock movements", True),
    _p("orders.manage", "merch", "Settle a payment for someone else's order", True),
    # --- fundraisers and tasks ---------------------------------------------------
    _p("fundraisers.view", "fundraisers", "See fundraisers, their income and their tasks"),
    _p("fundraisers.manage", "fundraisers", "Create and edit fundraisers"),
    _p("fundraisers.manage_all", "fundraisers", "Edit a fundraiser you do not own"),
    _p("income.log", "fundraisers", "Log fundraiser income into the ledger"),
    _p("tasks.view", "tasks", "See the task board"),
    _p("tasks.manage", "tasks", "Create, assign, move and delete any task"),
    _p("tasks.update_own", "tasks", "Move a task assigned to you"),
    # --- money -------------------------------------------------------------------
    _p("expenses.submit", "finance", "Submit an expense claim and manage your own claims"),
    _p("expenses.view_all", "finance", "See every expense claim"),
    _p("expenses.review", "finance", "Approve or reject an expense claim"),
    _p("expenses.reimburse", "finance", "Mark an approved claim as reimbursed"),
    _p("finance.view", "finance", "See the ledger, summaries and reports"),
    _p("finance.manage_entries", "finance", "Write manual ledger entries"),
    _p("finance.reverse", "finance", "Reverse a ledger entry"),
    _p("finance.allow_negative", "finance", "Write an entry that takes the balance below zero", True),
    _p("finance.close_period", "finance", "Create and close a finance period", True),
    _p("finance.close_period_force", "finance", "Close a period over unreconciled or pending claims", True),
    _p("finance.reopen_period", "finance", "Reopen a closed finance period", True),
    # --- assurance ------------------------------------------------------------------
    _p("audit.view", "assurance", "Read the audit trail"),
    _p("audit.export", "assurance", "Export the audit trail", True),
    _p("approvals.view", "assurance", "See approval requests", True),
    _p("approvals.decide", "assurance", "Approve or reject an approval request", True),
    # --- organization -----------------------------------------------------------------
    _p("committees.manage", "organization", "Create and edit committees and office positions", True),
    _p("terms.manage", "organization", "Create academic terms and run a handover", True),
    # --- assistant ------------------------------------------------------------------
    _p("assistant.use", "assistant", "Ask the club assistant for help"),
    _p("assistant.admin", "assistant", "Configure the club assistant", True),
    _p("knowledge.manage", "assistant", "Edit the assistant's knowledge base", True),
)

PERMISSIONS: frozenset[str] = frozenset(p.key for p in CATALOG)
PRIVILEGED_PERMISSIONS: frozenset[str] = frozenset(p.key for p in CATALOG if p.is_privileged)
BY_CATEGORY: dict[str, tuple[Permission, ...]] = {
    category: tuple(p for p in CATALOG if p.category == category)
    for category in dict.fromkeys(p.category for p in CATALOG)
}

# Fail at import, not at request time, if the catalog itself is malformed.
assert len(PERMISSIONS) == len(CATALOG), "duplicate permission key in CATALOG"


def describe(key: str) -> Permission:
    """The catalog row for a key. Raises on an unknown key - see `require_permission`."""
    for permission in CATALOG:
        if permission.key == key:
            return permission
    raise RuntimeError(f"unknown permission key: {key!r}")


def is_privileged(key: str) -> bool:
    return describe(key).is_privileged


@dataclass(frozen=True)
class RoleSpec:
    """A system role.

    `inherits` is what keeps the ladder honest: a role's effective permissions are its own `grants`
    plus every ancestor's, computed once at import. `is_privileged` is derived, not declared - a role
    is privileged exactly when it carries a privileged permission, so the two can never disagree.
    """

    key: str
    name: str
    description: str
    inherits: str | None = None
    grants: tuple[str, ...] = ()


# Ordered oldest-privilege-first; `grants_for` walks `inherits`, so the order here is for reading.
ROLE_SPECS: tuple[RoleSpec, ...] = (
    RoleSpec(
        "member",
        "Member",
        "A paid-up member: buys at member price, sees their own card, tickets and orders.",
        grants=("members.view",),
    ),
    RoleSpec(
        "volunteer",
        "Volunteer",
        "A member helping run an event or fundraiser: works assigned tasks, claims expenses, scans.",
        inherits="member",
        grants=(
            "members.verify",
            "tickets.checkin",
            "tasks.view",
            "tasks.update_own",
            "expenses.submit",
            "fundraisers.view",
        ),
    ),
    RoleSpec(
        "organizer",
        "Organizer",
        "Runs events and fundraisers: creates them, posts announcements, sees attendance.",
        inherits="volunteer",
        grants=(
            "users.lookup",
            "events.view_drafts",
            "events.manage_all",
            "attendees.view",
            "event_reports.view",
            "announcements.post",
            "announcements.manage",
            "announcements.view_all",
            "fundraisers.manage",
            "tasks.manage",
            "income.log",
        ),
    ),
    RoleSpec(
        "treasurer",
        "Treasurer",
        "Owns the money: reviews and reimburses claims, writes and reverses ledger entries.",
        inherits="organizer",
        grants=(
            "expenses.view_all",
            "expenses.review",
            "expenses.reimburse",
            "finance.view",
            "finance.manage_entries",
            "finance.reverse",
            "finance.close_period",
        ),
    ),
    RoleSpec(
        "admin",
        "Admin",
        "The committee leadership: manages members, plans, the shop and the finance periods.",
        inherits="treasurer",
        grants=(
            "users.view",
            "users.manage",
            "users.invite",
            "users.suspend",
            "roles.view",
            "roles.assign",
            "members.manage",
            "plans.manage",
            "fundraisers.manage_all",
            "announcements.view_deliveries",
            "products.manage",
            "merch_orders.manage",
            "stock.adjust",
            "orders.manage",
            "finance.reopen_period",
            # admin, not super_admin: today an admin may overdraw the balance and force a close, and
            # the golden matrix records that. Narrowing it here would be a silent privilege cut.
            "finance.allow_negative",
            "finance.close_period_force",
        ),
    ),
    RoleSpec(
        "super_admin",
        "Super admin (President)",
        "Everything, including role management and the audit trail. At least one must always exist.",
        inherits="admin",
        grants=(
            "roles.manage",
            "roles.assign_privileged",
            "system.settings",
            "audit.view",
            "audit.export",
            "approvals.view",
            "approvals.decide",
            "committees.manage",
            "terms.manage",
            "assistant.admin",
            "knowledge.manage",
        ),
    ),
    # --- outside the ladder ---------------------------------------------------------
    RoleSpec(
        "secretary",
        "Secretary",
        "Keeps the record: posts announcements, sees the member list and the committee structure.",
        inherits="member",
        grants=("announcements.post", "announcements.manage", "users.lookup", "committees.manage"),
    ),
    RoleSpec(
        "event_lead",
        "Event lead",
        "Runs one assigned event. Scoped: the assignment names the event, and only that one works.",
        inherits="volunteer",
        grants=("events.manage_own", "events.view_drafts", "attendees.view", "event_reports.view"),
    ),
    RoleSpec(
        "auditor",
        "Auditor",
        "Read-only oversight. Cannot write anything, anywhere - that is the point of the role.",
        grants=("members.view", "expenses.view_all", "finance.view", "event_reports.view", "audit.view"),
    ),
)

SYSTEM_ROLES: tuple[str, ...] = tuple(spec.key for spec in ROLE_SPECS)
_ROLE_BY_KEY: dict[str, RoleSpec] = {spec.key: spec for spec in ROLE_SPECS}

# The ladder, in rank order. `users.role` (the derived primary role) reports the highest of these a
# user holds, and `guest` when they hold none - which is exactly what an unpaid registrant is.
ROLE_RANK_ORDER: tuple[str, ...] = ("guest", "member", "volunteer", "organizer", "treasurer", "admin", "super_admin")
RANK: dict[str, int] = {key: index for index, key in enumerate(ROLE_RANK_ORDER)}


def grants_for(role_key: str) -> frozenset[str]:
    """A role's effective permissions: its own grants plus every ancestor's."""
    spec = _ROLE_BY_KEY.get(role_key)
    if spec is None:
        raise RuntimeError(f"unknown role key: {role_key!r}")
    keys = set(spec.grants)
    while spec.inherits:
        spec = _ROLE_BY_KEY[spec.inherits]
        keys |= set(spec.grants)
    return frozenset(keys)


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {spec.key: grants_for(spec.key) for spec in ROLE_SPECS}
PRIVILEGED_ROLES: frozenset[str] = frozenset(
    key for key, perms in ROLE_PERMISSIONS.items() if perms & PRIVILEGED_PERMISSIONS
)

assert all(
    key in PERMISSIONS for perms in ROLE_PERMISSIONS.values() for key in perms
), "a role grants a permission that is not in CATALOG"

# The legacy hierarchy, asserted rather than assumed: every step of the ladder must be a strict
# superset of the one below it. This is the property the golden matrix depends on.
for _lower, _higher in itertools.pairwise(ROLE_RANK_ORDER[1:]):
    assert ROLE_PERMISSIONS[_lower] < ROLE_PERMISSIONS[_higher], f"{_higher} must be a superset of {_lower}"
