"""Application configuration.

WHY THIS FILE EXISTS
--------------------
One typed, validated object holding every environment variable the system reads. It is the
single enforcement point for a rule from docs/11-coding-standards.md § Configuration:

    **The process must REFUSE TO BOOT if a required variable is missing.**

That is not pedantry. A service that starts fine and then fails on first use pages you at 3am
when the first customer hits it. A service that refuses to start fails in the deploy pipeline,
in front of the engineer who caused it, with a clear message. Same bug; wildly different cost.

DESIGN DECISIONS
----------------
1. `pydantic-settings` over `os.getenv()`:
   - `os.getenv("DATABASE_POOL_SIZE")` returns a `str | None`. Somewhere downstream, someone
     writes `int(...)` and it explodes at runtime. Pydantic parses and validates at BOOT.
   - Types are enforced. `DATABASE_ECHO=maybe` fails immediately with a useful error.

2. NO DEFAULTS FOR SECRETS. Note that non-secret values (pool size, log level) have sensible
   defaults, but anything sensitive is a required field. A default secret is a secret that
   ships to production by accident.

3. `@lru_cache` on `get_settings()`: the object is built ONCE per process. It is injected as
   a dependency, never imported as a module-level global — so a test can override it without
   monkeypatching the world (docs/11 § Dependency injection).

4. `ENVIRONMENT` drives *infrastructure* behaviour (log format, docs exposure) — never
   business behaviour. There is no `if settings.environment == "production"` anywhere in the
   domain. Behavioural differences are INJECTED DEPENDENCIES (FakeEmailClient vs ResendClient),
   chosen once, at the composition root.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    """Where this process is running.

    A StrEnum (not a bare `str`) so that a typo like ENVIRONMENT=prodcution fails at boot
    instead of silently taking the "not production" branch — which would, for example, leave
    the interactive API docs exposed on a public endpoint.
    """

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Every environment variable the system reads. See `.env.example` for documentation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Reject unknown env vars? No — the OS environment is full of PATH, HOME, etc.
        # But we DO reject unknown fields in API schemas, where they indicate a client bug.
        extra="ignore",
    )

    # --- Runtime ---
    environment: Environment = Environment.LOCAL
    log_level: LogLevel = LogLevel.INFO

    # --- Database ---
    # PostgresDsn validates the URL SHAPE at boot. A typo'd DSN fails here, not on the first
    # query at 3am.
    database_url: PostgresDsn
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_echo: bool = False

    # --- Redis ---
    redis_url: RedisDsn

    # --- API ---
    api_host: str = (
        "0.0.0.0"  # noqa: S104 — binding all interfaces is correct inside a container
    )
    api_port: int = 8000
    # NoDecode stops pydantic-settings from JSON-decoding the env var before our
    # comma-splitting validator below gets to see it.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        """Accept `CORS_ORIGINS=http://a.com,http://b.com` from the environment.

        Env vars are always strings; there is no native list type. Pydantic would try to
        JSON-decode this, which forces an unpleasant `["http://a.com"]` in your .env file.
        Comma-separated is what every other tool expects, so we meet that expectation.
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # --- Derived properties -------------------------------------------------
    # Expressed as properties, not stored fields, so they cannot drift out of sync with
    # `environment` and cannot be overridden independently.

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def is_local(self) -> bool:
        return self.environment is Environment.LOCAL

    @property
    def docs_enabled(self) -> bool:
        """Expose /docs and /openapi.json?

        NOT in production. The OpenAPI schema is a complete, machine-readable map of every
        endpoint, parameter and error for an attacker. It is enormously useful in dev and
        gratuitous attack-surface disclosure in prod. The frontend consumes the schema at
        BUILD time (`make types`), never at runtime, so nothing breaks by hiding it.
        """
        return not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Cached because parsing and validating the environment on every request would be wasteful
    and, worse, would let configuration change mid-process — a source of genuinely baffling
    bugs.

    This function is the ONLY way to obtain Settings. It is wired in at the composition root
    (FastAPI `Depends`, ARQ context) and injected downward. Nothing in `core` reaches for it
    at module scope; that would make the object impossible to fake in a test.
    """
    return Settings()
