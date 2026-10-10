import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("ssa.config")

# What ships in `.env.example`. A production deployment still carrying one of these is not
# configured, it is copied - and a JWT_SECRET everybody can read is not a secret.
PLACEHOLDERS = frozenset(
    {
        "dev-only-change-me",
        "change-me",
        "changeme",
        "secret",
        "your-project-ref",
        "<password>",
        "your-service-role-key",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # development | test | production. Production turns the warnings in `startup_problems()` into
    # a refusal to boot; see `enforce_startup_config()`.
    APP_ENV: str = "development"
    DEBUG: bool = False

    # Supabase needs two connection strings, and they are not interchangeable:
    #   DATABASE_URL - the TRANSACTION pooler (port 6543). The running app uses this, because a
    #                  serverless-style deploy opens far more connections than Postgres would
    #                  accept directly. Each statement may land on a different backend, so the
    #                  engine disables prepared statements (see core/db.py).
    #   DIRECT_URL   - the SESSION pooler (port 5432). Alembic and scripts/seed.py use ONLY this:
    #                  DDL and long transactions cannot survive transaction pooling.
    # Locally the two are simply the same URL, and DIRECT_URL can be left unset.
    DATABASE_URL: str = "sqlite:///./ssa_hub.db"
    DIRECT_URL: str | None = None
    # Tests get their own database. conftest.py refuses to run at all unless this is set and
    # points somewhere other than DATABASE_URL, so a test run can never truncate real data.
    TEST_DATABASE_URL: str | None = None

    JWT_SECRET: str = "dev-only-change-me"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    BCRYPT_ROUNDS: int = 12  # tests lower this to keep the suite fast

    # Where the SPA lives - announcement emails link back to it.
    FRONTEND_URL: str = "http://localhost:5173"
    # console | (M2: resend, smtp). See services/mailer.py.
    EMAIL_PROVIDER: str = "console"
    UNSUBSCRIBE_TOKEN_DAYS: int = 3650  # an unsubscribe link must not expire while it is in an inbox

    # Merch is members-only by default (PRD FR-4.1). Set false to let anyone order at list price.
    MERCH_MEMBERS_ONLY: bool = True

    # Receipts (Phase 6). The bucket is PRIVATE and only this backend holds the key, so
    # SUPABASE_SERVICE_ROLE_KEY must never be logged, returned, or committed - it bypasses RLS.
    # `local` keeps the whole receipt flow working with no cloud account (dev and tests).
    STORAGE_PROVIDER: str = "local"
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    RECEIPTS_BUCKET: str = "receipts"
    LOCAL_STORAGE_DIR: str = "var/storage"
    # Signed URLs are minted per request and are good for ten minutes - long enough to open the
    # link, short enough that a URL pasted into a group chat is dead by the time anyone clicks it.
    RECEIPT_URL_TTL_SECONDS: int = 600
    # A claim may be dated up to this far back; a semester's receipts do not arrive same-day.
    EXPENSE_BACKDATE_DAYS: int = 90

    # --- Rate limits (Phase 7) ---------------------------------------------------------------
    # In memory, per process. The app runs as ONE worker (see the scheduler note in jobs/), so a
    # process-local counter is a real limit; M2 moves this to Redis when there is more than one.
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_PER_MINUTE: int = 10
    REGISTER_PER_MINUTE: int = 10
    LOGIN_FAILURES_BEFORE_LOCKOUT: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    CHECKIN_PER_MINUTE: int = 120
    CHECKOUT_PER_MINUTE: int = 30

    # Password policy: at least this many characters, and at least one letter and one digit.
    PASSWORD_MIN_LENGTH: int = 8
    MIN_JWT_SECRET_LENGTH: int = 32

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def migration_url(self) -> str:
        """What Alembic and scripts/seed.py connect to. Falls back to DATABASE_URL when the
        deployment has only one URL (local Postgres, SQLite, CI)."""
        return self.DIRECT_URL or self.DATABASE_URL

    def startup_problems(self) -> list[str]:
        """Everything wrong with this configuration, as sentences. Empty means good to go.

        Split out from the enforcement so it can be tested without stopping a process, and so the
        same list can be a warning in development and a refusal in production.
        """
        problems = []
        secret = (self.JWT_SECRET or "").strip()
        if secret.lower() in PLACEHOLDERS:
            problems.append("JWT_SECRET is still the placeholder from .env.example")
        elif len(secret) < self.MIN_JWT_SECRET_LENGTH:
            problems.append(f"JWT_SECRET is shorter than {self.MIN_JWT_SECRET_LENGTH} characters")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS contains '*' (any site could call this API with credentials)")
        if self.DEBUG:
            problems.append("DEBUG is on")
        if not (self.EMAIL_PROVIDER or "").strip():
            problems.append("EMAIL_PROVIDER is unset")
        if not (self.STORAGE_PROVIDER or "").strip():
            problems.append("STORAGE_PROVIDER is unset")
        if self.STORAGE_PROVIDER == "supabase" and not (self.SUPABASE_SERVICE_ROLE_KEY or "").strip():
            problems.append("STORAGE_PROVIDER=supabase but SUPABASE_SERVICE_ROLE_KEY is unset")
        return problems

    def enforce_startup_config(self) -> list[str]:
        """Called once at startup. A misconfigured development machine gets a loud warning; a
        misconfigured production deployment does not start at all - failing at boot is far cheaper
        than serving traffic signed with a public secret."""
        problems = self.startup_problems()
        if not problems:
            return []
        if self.is_production:
            raise RuntimeError("refusing to start with APP_ENV=production: " + "; ".join(problems))
        for problem in problems:
            log.warning("config: %s", problem)
        return problems


settings = Settings()
