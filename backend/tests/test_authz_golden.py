"""Replay the pre-refactor authorisation matrix and prove nothing moved by accident.

The fixture in tests/fixtures/authz_golden.json was recorded from the code as it stood before the
permission-based RBAC work. Every cell in it is an allow/deny answer for one (route, legacy role)
pair, and this test re-runs all 558 of them.

A cell is allowed to change only if tests/fixtures/authz_intended_changes.json names it with a
reason. Anything else is a regression in the refactor, not a decision.
"""

from __future__ import annotations

import pytest

from app.main import app
from tests.authz_golden import collect, diff, load_golden, load_intended, make_harness


@pytest.fixture
def harness(pg_engine):
    client, reset = make_harness(app, pg_engine)
    yield client, reset
    app.dependency_overrides.clear()


def test_authorisation_is_unchanged(harness):
    client, reset = harness
    golden = load_golden()
    current = collect(client, app, reset)

    problems = diff(golden, current, load_intended())
    assert not problems, (
        f"{len(problems)} authorisation change(s) not declared in "
        f"tests/fixtures/authz_intended_changes.json:\n  " + "\n  ".join(problems)
    )


def test_the_golden_matrix_still_covers_every_route(harness):
    """A route added after the fixture was recorded has no recorded answer, and `diff` would only
    notice it as an extra key. Stated separately so it reads as its own failure."""
    from tests.authz_golden import route_keys

    golden = set(load_golden()["routes"])
    live = {f"{method} {path}" for method, path in route_keys(app)}
    assert live <= golden, f"routes with no recorded authorisation: {sorted(live - golden)}"
