"""Central, typed configuration.

Every runtime setting the platform needs is resolved here from environment
variables / ``.env`` (via :mod:`pydantic_settings`) or from the JSON source
registry.  Nothing downstream is allowed to hardcode a path, credential,
threshold or dataset name — it must come through :class:`Settings` or
:func:`load_source_registry`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (etl/common/config.py -> project).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Environment ─────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # ── Paths ───────────────────────────────────────────────────────────────
    datasets_dir: str = "datasets/data-engineering-sample-teams-scenario"
    lakehouse_dir: str = "lakehouse"
    bronze_dir: str = "lakehouse/bronze"
    silver_dir: str = "lakehouse/silver"
    gold_dir: str = "lakehouse/gold"
    quarantine_dir: str = "lakehouse/quarantine"
    reports_dir: str = "reports"
    logs_dir: str = "logs"
    config_dir: str = "config"

    # ── Pipeline behaviour ──────────────────────────────────────────────────
    parquet_compression: str = "snappy"
    retry_count: int = 3
    retry_backoff_seconds: float = 2.0
    chunk_size: int = 100_000

    # ── Quality thresholds ──────────────────────────────────────────────────
    quality_min_schema_valid: float = 0.95
    quality_min_relationship_valid: float = 0.90
    quality_max_duplicate_ratio: float = 0.05
    quality_max_missing_ratio: float = 0.30

    # ── Business rules ──────────────────────────────────────────────────────
    non_direct_ratio_threshold: float = 0.20
    allocation_min: int = 0
    allocation_max: int = 100

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "acme_analytics"
    postgres_user: str = "acme"
    postgres_password: str = "change_me"
    database_url: str = ""

    # ── Derived, absolute paths ─────────────────────────────────────────────
    def _abs(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    @computed_field  # type: ignore[misc]
    @property
    def datasets_path(self) -> Path:
        return self._abs(self.datasets_dir)

    @computed_field  # type: ignore[misc]
    @property
    def bronze_path(self) -> Path:
        return self._abs(self.bronze_dir)

    @computed_field  # type: ignore[misc]
    @property
    def silver_path(self) -> Path:
        return self._abs(self.silver_dir)

    @computed_field  # type: ignore[misc]
    @property
    def gold_path(self) -> Path:
        return self._abs(self.gold_dir)

    @computed_field  # type: ignore[misc]
    @property
    def quarantine_path(self) -> Path:
        return self._abs(self.quarantine_dir)

    @computed_field  # type: ignore[misc]
    @property
    def reports_path(self) -> Path:
        return self._abs(self.reports_dir)

    @computed_field  # type: ignore[misc]
    @property
    def logs_path(self) -> Path:
        return self._abs(self.logs_dir)

    @computed_field  # type: ignore[misc]
    @property
    def config_path(self) -> Path:
        return self._abs(self.config_dir)

    @property
    def sqlalchemy_url(self) -> str:
        """Full SQLAlchemy URL — explicit ``DATABASE_URL`` wins, else derived."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def ensure_directories(self) -> None:
        """Create every lakehouse / output directory if missing (idempotent)."""
        for path in (
            self.bronze_path,
            self.silver_path,
            self.gold_path,
            self.quarantine_path,
            self.reports_path,
            self.logs_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()


def load_source_registry(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Load the source-system registry (``config/sources.json``).

    Returns a list of source descriptors. The registry is the single source of
    truth for which raw datasets exist and how to read them.
    """
    settings = settings or get_settings()
    registry_file = settings.config_path / "sources.json"
    if not registry_file.exists():
        raise FileNotFoundError(f"Source registry not found: {registry_file}")
    with registry_file.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    sources = payload.get("sources", [])
    if not sources:
        raise ValueError(f"Source registry {registry_file} contains no sources.")
    return sources
