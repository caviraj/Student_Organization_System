from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def migration_url(self) -> str:
        """What Alembic and scripts/seed.py connect to. Falls back to DATABASE_URL when the
        deployment has only one URL (local Postgres, SQLite, CI)."""
        return self.DIRECT_URL or self.DATABASE_URL


settings = Settings()
