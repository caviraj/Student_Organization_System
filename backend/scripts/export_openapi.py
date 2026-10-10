"""Write `docs/openapi.json` from the app itself.

    python scripts/export_openapi.py [--check]

The frontend generates its TypeScript types from this file, so it has to be a pure function of the
code: same source in, byte-identical file out. `json.dumps(sort_keys=True)` is what guarantees that
- FastAPI's own dict ordering follows route registration, which changes whenever a router is added,
and an unstable file would show up as a diff on every unrelated PR.

`--check` writes nothing and exits non-zero if the committed file is stale, which is what a CI job
(or a reviewer) runs to prove the handoff is current.
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app

DEST = BACKEND_DIR.parent / "docs" / "openapi.json"


def render() -> str:
    # sort_keys is the determinism; indent is so a human diff of this file is readable.
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    rendered = render()
    if "--check" in sys.argv:
        if not DEST.exists():
            print(f"  FAIL: {DEST} does not exist - run `python scripts/export_openapi.py`")
            return 1
        if DEST.read_text(encoding="utf-8") != rendered:
            print(f"  FAIL: {DEST.name} is stale - run `python scripts/export_openapi.py`")
            return 1
        print(f"  OK: {DEST.name} is up to date")
        return 0

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(rendered, encoding="utf-8")
    paths = len(app.openapi()["paths"])
    print(f"  wrote {DEST} ({paths} paths, {len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
