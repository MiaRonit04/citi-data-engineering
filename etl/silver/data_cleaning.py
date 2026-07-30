"""Generic, reusable cleaning primitives.

These are **pure functions** over pandas Series/DataFrames — no IO, no config
side effects — so they are trivially unit-testable and composable. Every rule
here is documented in ``docs/CLEANING_RULES.md`` and covered by tests.

The functions are deliberately conservative: they normalise *representation*
(whitespace, casing, null tokens, invisible characters) but never invent or
drop data. Records are only ever removed by explicit dedupe / quarantine steps.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Tokens that represent "no value" across the source systems. Compared
# case-insensitively after trimming.
NULL_TOKENS: frozenset[str] = frozenset(
    {"", "na", "n/a", "n.a.", "none", "null", "nil", "unknown", "unspecified", "-", "--"}
)

# Zero-width / invisible unicode characters that sneak into exported CSVs.
_INVISIBLE = dict.fromkeys(
    map(ord, ["​", "‌", "‍", "﻿", " ", "⁠"]), None
)
_MULTISPACE = re.compile(r"\s+")


def strip_invisible(value: object) -> object:
    """Remove zero-width / non-breaking-space characters; NBSP → normal space."""
    if not isinstance(value, str):
        return value
    return value.replace(" ", " ").translate(_INVISIBLE)


def normalize_whitespace(value: object) -> object:
    """Trim ends and collapse any internal whitespace run to a single space."""
    if not isinstance(value, str):
        return value
    return _MULTISPACE.sub(" ", value).strip()


def normalize_unicode(value: object) -> object:
    """Apply NFKC normalization so visually-identical strings compare equal."""
    if not isinstance(value, str):
        return value
    return unicodedata.normalize("NFKC", value)


def to_null_if_token(value: object) -> object:
    """Return ``None`` if ``value`` is a recognised null-token, else unchanged."""
    if not isinstance(value, str):
        return value
    return None if value.strip().lower() in NULL_TOKENS else value


def clean_text(value: object) -> object:
    """Full text-cleaning chain: unicode → invisible → whitespace → null-token."""
    value = normalize_unicode(value)
    value = strip_invisible(value)
    value = normalize_whitespace(value)
    value = to_null_if_token(value)
    return value


def clean_text_series(series: pd.Series) -> pd.Series:
    """Vectorised :func:`clean_text` over a Series (object dtype preserved)."""
    return series.map(clean_text)


def clean_text_columns(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Return a copy of ``df`` with text-cleaning applied to ``columns``.

    ``columns=None`` cleans every object/string column. Non-text columns are
    left untouched.
    """
    out = df.copy()
    cols = columns if columns is not None else [
        c for c in out.columns if out[c].dtype == object or str(out[c].dtype).startswith("string")
    ]
    for col in cols:
        if col in out.columns:
            out[col] = clean_text_series(out[col])
    return out


def title_case(value: object) -> object:
    """Title-case a cleaned string (e.g. ``FINANCE`` / ``finance`` → ``Finance``).

    Preserves already-null values and normalises internal spacing first.
    """
    value = normalize_whitespace(value)
    if not isinstance(value, str) or value == "":
        return None if value == "" else value
    return value.title()
