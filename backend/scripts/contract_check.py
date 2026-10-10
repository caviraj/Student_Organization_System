"""Prove `docs/DESIGN.md` §5 and the running app agree, in both directions.

    python scripts/contract_check.py      # exits non-zero on any disagreement

DESIGN.md §5 is the contract the frontend is being built against, and the app is the thing that
actually answers. They drift silently: a rename on one side, a new route nobody documented, a
`require_role` moved down a level. This compares the two and prints three lists:

  * **documented, not implemented** - the frontend will call it and get a 404
  * **implemented, not documented** - exists, but no teammate knows about it
  * **role mismatch** - the row says one minimum role, the route enforces another. This is the
    dangerous one in one direction: a route that is *weaker* than documented is an open door.

Two things it deliberately does not check. **Response bodies** - DESIGN documents those in prose,
and a machine-readable comparison would mean rewriting the contract as JSON Schema, which is not
what a frontend developer wants to read. **Per-row rules** - "the owner, or an admin", "the
assignee for `status` only" are service-level checks that cannot be read off a dependency tree;
those rows are counted separately so their absence from the role check is visible, not silent.

Rows whose Notes column mentions M2 are skipped: they are documented future work (the Razorpay
webhook), not a contract the frontend can call today.
"""

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.authz import PERMISSION_FLOOR
from app.core.deps import ROLE_RANK, get_current_user, get_optional_user
from app.core.routes import iter_api_routes
from app.main import app

DESIGN = BACKEND_DIR.parent / "docs" / "DESIGN.md"
API_PREFIX = "/api/v1"

RANK_NAME = {rank: role for role, rank in ROLE_RANK.items()}

# The Role column, reduced to the one word that can be compared. Longer cells ("authorizer+ and
# the owner, or an admin") compare on their FIRST token, which is the floor the route enforces.
ROLE_WORDS = {
    "public": "public",
    "auth": "auth",
    "any": "auth",
    "member": "member",
    "volunteer+": "volunteer",
    "organizer+": "organizer",
    "treasurer+": "treasurer",
    "admin": "admin",
}


def collapse_params(path: str) -> str:
    """`/plans/{plan_id}` and `/plans/{id}` are the same route: the parameter's name is FastAPI's
    business, not the contract's."""
    return re.sub(r"\{[^}]*\}", "{}", path)


def design_path(raw: str) -> str:
    """A Design.md path cell, as a comparable key. Query strings and trailing prose are dropped."""
    path = raw.strip().strip("`").split("?")[0].split(" ")[0].strip()
    if not path.startswith("/"):
        path = "/" + path
    return collapse_params(path if path in ("/health",) else API_PREFIX + path)


def design_rows(text: str) -> tuple[list[tuple[str, str, str, str]], int]:
    """`[(method, path, role, notes)]` from the §5 tables, plus how many were skipped as M2."""
    rows: list[tuple[str, str, str, str]] = []
    skipped = 0
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.startswith("## 5.")
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        method_cell, path_cell, role_cell, notes = cells[0], cells[1], cells[2], cells[3]
        methods = re.findall(r"\b(?:GET|POST|PUT|PATCH|DELETE)\b", method_cell)
        if not methods:
            continue  # the header row, or a separator
        if re.search(r"\bM2\b", notes):
            skipped += 1
            continue
        paths = [p for p in re.split(r"[,·]", path_cell) if p.strip()]
        for method in methods:
            for path in paths:
                rows.append((method, design_path(path), role_cell, notes))
    return rows, skipped


def implemented_role(route) -> tuple[str | None, bool]:
    """The floor this route enforces, as one of the words in `ROLE_WORDS`.

    Returns `(role, is_machine_checkable)`. `require_permission(...)` marks its dependency with the
    keys it accepts; each key is reduced to the lowest-ranked ladder role that holds it, which is
    the role the DESIGN.md cell names. `require_role(...)` is still read for anything left on the
    old dependency; a bare `get_current_user` means "any authenticated user"; `get_optional_user`
    means the route is public but personalises when a token is present.
    """
    roles: set[str] = set()
    floors: set[str] = set()
    authenticated = False
    optional = False

    def walk(dependant) -> None:
        nonlocal authenticated, optional
        call = dependant.call
        if call is not None:
            declared = getattr(call, "required_roles", None)
            if declared:
                roles.update(declared)
            keys = getattr(call, "required_permissions", None)
            if keys:
                # A route reachable two ways ("manage any event" or "manage your own") is as weak as
                # its weakest door, so the floor is the lowest one any accepted key gives.
                floors.update(floor for key in keys if (floor := PERMISSION_FLOOR.get(key)))
            if call is get_current_user:
                authenticated = True
            if call is get_optional_user:
                optional = True
        for sub in dependant.dependencies:
            walk(sub)

    walk(route.dependant)
    candidates = list(roles) + list(floors)
    if candidates:
        return RANK_NAME[min(ROLE_RANK[role] for role in candidates)], True
    if optional:
        return "public", True
    if authenticated:
        return "auth", True
    return "public", True


def design_role(cell: str) -> str | None:
    """The comparable word from the Role column, or None when the rule is per-row.

    `owner`, `provider` and friends are enforced in a service against a row, so there is nothing
    here to compare - returning None keeps them out of the role check rather than guessing.
    """
    cleaned = cell.replace("*", "").strip().lower()
    for word, role in ROLE_WORDS.items():
        if cleaned.startswith(word):
            return role
    return None


def main() -> int:
    rows, skipped_m2 = design_rows(DESIGN.read_text(encoding="utf-8"))
    documented: dict[tuple[str, str], str | None] = {}
    uncheckable: set[tuple[str, str]] = set()
    for method, path, role_cell, _ in rows:
        key = (method, path)
        role = design_role(role_cell)
        documented[key] = role
        if role is None:
            uncheckable.add(key)

    implemented: dict[tuple[str, str], str] = {}
    for path, route in iter_api_routes(app):
        for method in route.methods or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            implemented[(method, collapse_params(path))] = implemented_role(route)[0]

    missing = sorted(set(documented) - set(implemented))
    undocumented = sorted(set(implemented) - set(documented))
    mismatches = []
    for key in sorted(set(documented) & set(implemented)):
        expected = documented[key]
        if expected is None:
            continue
        actual = implemented[key]
        if expected != actual:
            mismatches.append((key, expected, actual))

    print("SSA Hub - API contract check (docs/DESIGN.md §5 vs app.openapi())")
    print("-" * 72)
    print(
        f"  documented {len(documented):>3}   implemented {len(implemented):>3}   matched {len(set(documented) & set(implemented)):>3}"
    )
    print(f"  per-row role rules (owner/assignee/...) not machine-checkable: {len(uncheckable)}")
    print(f"  rows deferred to M2 and skipped: {skipped_m2}")
    print("-" * 72)

    if missing:
        print(f"  DOCUMENTED, NOT IMPLEMENTED ({len(missing)}):")
        for method, path in missing:
            print(f"    {method:<6} {path}")
    if undocumented:
        print(f"  IMPLEMENTED, NOT DOCUMENTED ({len(undocumented)}):")
        for method, path in undocumented:
            print(f"    {method:<6} {path}   (role: {implemented[(method, path)]})")
    if mismatches:
        print(f"  ROLE MISMATCH ({len(mismatches)}):")
        for (method, path), expected, actual in mismatches:
            weaker = ROLE_RANK.get(actual, -1) < ROLE_RANK.get(expected, -1)
            note = "  <-- WEAKER THAN DOCUMENTED" if weaker and actual in ROLE_RANK else ""
            print(f"    {method:<6} {path}   doc: {expected}   code: {actual}{note}")

    if missing or undocumented or mismatches:
        print("-" * 72)
        print("  FAIL: the contract and the app disagree - fix one of them, not both")
        return 1
    print("  OK: every documented route exists with the documented role, and nothing is hidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
