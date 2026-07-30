"""Optional PostgreSQL source ingestion for Bronze.

The reference scenario ships as files, but Bronze is designed to also land
relational sources. This module reads a whole table (or a SQL query) into a
raw string DataFrame so it can flow through the identical Bronze writer.

It is intentionally dependency-light: SQLAlchemy is imported lazily so the
file-only path never requires a database.
"""

from __future__ import annotations

import pandas as pd

from etl.common.config import Settings, get_settings
from etl.common.exceptions import IngestionError
from etl.common.logging import get_logger


def read_table(table: str, settings: Settings | None = None) -> pd.DataFrame:
    """Read an entire PostgreSQL table as raw strings.

    Parameters
    ----------
    table:
        Fully-qualified or bare table name.
    """
    settings = settings or get_settings()
    log = get_logger("bronze", dataset=table)
    try:
        from sqlalchemy import create_engine, text  # lazy import
    except ImportError as exc:  # pragma: no cover
        raise IngestionError("SQLAlchemy is required for PostgreSQL ingestion") from exc

    engine = create_engine(settings.sqlalchemy_url)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(f'SELECT * FROM {table}'), conn)  # noqa: S608 - table from trusted config
    except Exception as exc:  # noqa: BLE001
        raise IngestionError(f"Failed to read table '{table}': {exc}") from exc
    finally:
        engine.dispose()

    log.debug("Read {rows} rows from postgres table {table}", rows=len(df), table=table)
    # Preserve rawness — everything to string, like the file readers.
    return df.astype("string").astype(object).where(df.notna(), None)
