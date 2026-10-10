"""Scan every tracked file for anything that looks like a live credential.

    python scripts/secret_scan.py            # exits non-zero on a hit

Only files git tracks are scanned, because only those can be pushed: a stray `.env` on a developer's
disk is a local file, while a key inside a tracked file is a leak the moment the branch is pushed.
`git ls-files` is the definition of "can be pushed", so this cannot disagree with what git does.

The point is to catch a REAL secret, not to make placeholders annoying, so every rule carries the
placeholder shapes it must ignore - `change-me`, `<password>`, `postgres:postgres`. A file that
documents a placeholder is doing the right thing and must not be flagged; the same file carrying an
actual key is what fails the build.

Run it from the repo root or from `backend/` - it finds the top level itself.
"""

import re
import subprocess
import sys
from pathlib import Path

# Anything a rule matches must not be one of these bare words, or it is documentation.
PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "dev-only-change-me",
        "secret",
        "your-project-ref",
        "your-service-role-key",
        "your-anon-key",
        "password",
        "pass",
        "postgres",
        "user",
        "xxx",
        "...",
        "<password>",
        "<your-password>",
        "<service-role-key>",
        "",
    }
)

# Lines ending in one of these are prose about the rule, not a value.
SKIP_MARKERS = ("secret_scan.py",)

RULES: list[tuple[str, re.Pattern]] = [
    # A JWTs three dot-separated base64url segments. Supabase's anon and service keys are both
    # this shape, which is exactly why they leak so easily into frontend code and screenshots.
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    # Supabase's newer key format.
    ("supabase-key", re.compile(r"\bsb_(secret|publishable)_[A-Za-z0-9_-]{16,}\b")),
    # A Postgres URL that actually carries a password (postgres://user:pass@host).
    ("postgres-url-with-password", re.compile(r"\bpostgres(?:ql)?(?:\+\w+)?://([^\s:/@]+):([^\s:/@]+)@")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # Anything assigned to a name that says "this is a credential", where the value is long enough
    # to be real rather than a word like "local" or "console".
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(JWT_SECRET|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_ANON_KEY|SECRET_KEY|API_KEY|"
            r"ACCESS_TOKEN|DATABASE_URL|DIRECT_URL)\b\s*[=:]\s*[\"']?([^\s\"'#]{12,})"
        ),
    ),
]

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".sh",
    ".sql",
    ".toml",
    ".ini",
    ".cfg",
    ".yml",
    ".yaml",
    ".html",
    ".css",
    ".txt",
    ".env",
    ".example",
}
TEXT_NAMES = {".env", ".env.example", ".gitignore", "Dockerfile", "Makefile"}


def repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if out.returncode == 0:
        return Path(out.stdout.strip())
    return Path(__file__).resolve().parents[2]


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        return [path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]
    return [root / line for line in out.stdout.splitlines() if line.strip()]


def is_placeholder(value: str) -> bool:
    stripped = value.strip().strip("\"'").lower()
    if stripped in PLACEHOLDERS:
        return True
    # `your-...`, `<...>`, `xxxx` and `***` are all shapes of "fill this in".
    return stripped.startswith(("your-", "your_", "<", "xxx", "***")) or set(stripped) <= {"x", "*", "."}


# A Postgres URL is only a leak if its password could plausibly be a real one. `ssa:ssa@localhost`
# is the documented local default in .env.example, and failing on it would train everyone to
# ignore this script.
MIN_URL_PASSWORD = 8


def scan_text(path: Path, text: str) -> list[tuple[int, str, str]]:
    """`[(line number, rule, offending text)]`. The text is truncated: a secret in a report is a
    second copy of the secret."""
    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        if any(marker in str(path) for marker in SKIP_MARKERS):
            continue
        for rule, pattern in RULES:
            match = pattern.search(line)
            if not match:
                continue
            if rule == "postgres-url-with-password":
                password = match.group(2)
                if is_placeholder(password) or len(password) < MIN_URL_PASSWORD:
                    continue
            else:
                captured = match.group(match.lastindex or 0)
                if is_placeholder(captured):
                    continue
                # A URL is judged by the rule above, on its password, not on its length.
                if "://" in captured:
                    continue
            hits.append((number, rule, line.strip()[:80]))
            break
    return hits


# A scanner that never fires is indistinguishable from a clean repo, so `--self-test` proves it
# still catches the five things it exists for - and still ignores the four it must not flag.
MUST_HIT = [
    'token = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.abc123def456"',
    "SUPABASE_SERVICE_ROLE_KEY=sb_secret_AbCdEf0123456789xyz",
    "DATABASE_URL=postgresql://postgres:hunter2hunter2@db.abcdefgh.supabase.co:5432/postgres",
    "-----BEGIN RSA PRIVATE KEY-----",
    "JWT_SECRET=9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c",
]
MUST_MISS = [
    "JWT_SECRET=dev-only-change-me",
    "DATABASE_URL=postgresql+psycopg://ssa:ssa@localhost:5432/ssa_hub",
    "SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>",
    "# DATABASE_URL=sqlite:///./ssa_hub.db",
]


def self_test() -> int:
    print("SSA Hub - secret scan self-test")
    print("-" * 64)
    failed = 0
    for sample in MUST_HIT:
        if not scan_text(Path("sample.py"), sample):
            print(f"  MISS: should have been caught -> {sample[:60]}")
            failed += 1
    for sample in MUST_MISS:
        if scan_text(Path("sample.py"), sample):
            print(f"  FALSE POSITIVE -> {sample[:60]}")
            failed += 1
    print("-" * 64)
    if failed:
        print(f"  FAIL: {failed} of {len(MUST_HIT) + len(MUST_MISS)} samples wrong")
        return 1
    print(f"  OK: {len(MUST_HIT)} caught, {len(MUST_MISS)} correctly ignored")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    root = repo_root()
    print(f"SSA Hub - secret scan ({root})")
    print("-" * 64)
    scanned = 0
    hits: list[str] = []
    for path in tracked_files(root):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for number, rule, snippet in scan_text(path, text):
            hits.append(f"{path.relative_to(root)}:{number}: {rule} -> {snippet}")
    print(f"  scanned {scanned} tracked text files")
    print("-" * 64)
    if hits:
        print(f"  FAIL: {len(hits)} possible secret(s):")
        for hit in hits:
            print(f"    {hit}")
        print("\n  If one of these is a real credential, rotate it before doing anything else:")
        print("  it is already in the git history until it is rotated.")
        return 1
    print("  OK: no live credentials found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
