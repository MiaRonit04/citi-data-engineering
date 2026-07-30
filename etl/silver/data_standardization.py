"""Standardization primitives: dates, months, emails, categoricals, numerics.

Where cleaning normalises *representation*, standardization normalises *meaning*
into canonical, analytics-ready forms:

* dates  → ``YYYY-MM-DD``
* months → ``YYYY-MM``
* emails → canonical join key (case/whitespace/domain normalised)
* categoricals (department, employment_type) → canonical label
* team_code (`tm006`) → canonical `TM-006`
* numerics → typed, with configurable bounds enforcement

All functions return ``(value, ok)`` or annotate a companion boolean so the
pipeline can *count and report* every coercion instead of silently mutating.
"""

from __future__ import annotations

import re
from datetime import datetime

import numpy as np
import pandas as pd

from etl.silver.data_cleaning import normalize_whitespace

# ── Dates ───────────────────────────────────────────────────────────────────
# Explicit formats observed during profiling, tried in order. Explicit formats
# avoid dateutil's ambiguous guessing (e.g. day/month order).
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",        # 2018-08-10
    "%Y/%m/%d",        # 2024/02/01
    "%m/%d/%Y",        # 11/18/2016
    "%d-%b-%Y",        # 22-Jan-2021
    "%d-%b-%y",        # 01-Feb-24
    "%b %d %Y",        # Feb 1 2026
    "%B %d, %Y",       # February 10, 2024
    "%B %d %Y",        # February 10 2024
    "%d %b %Y",        # 1 Feb 2024
    "%d/%m/%Y",        # 01/02/2024 (fallback, EU) — tried last
)


def parse_date(value: object) -> str | None:
    """Parse a single date value to ISO ``YYYY-MM-DD`` or ``None``.

    Tries each known format in order. A value that is already null-like returns
    ``None``. Unparseable non-empty values also return ``None`` (the caller
    counts these as coercion failures — never a guess).
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = normalize_whitespace(str(value))
    if text == "":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def standardize_date_series(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Vectorised date standardization.

    Returns ``(iso_series, failed_mask)`` where ``failed_mask`` is True for
    values that were non-empty but could not be parsed (data-quality signal).
    """
    original_nonblank = series.map(lambda v: normalize_whitespace(str(v)) != "" if v is not None else False)
    iso = series.map(parse_date)
    failed = original_nonblank & iso.isna()
    return iso, failed


_MONTH_NAME_RE = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], start=1)}


def parse_month(value: object) -> str | None:
    """Parse a month value to ``YYYY-MM`` (handles ``2026-07`` and ``March 2026``)."""
    if value is None:
        return None
    text = normalize_whitespace(str(value))
    if text == "":
        return None
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return text
    m = _MONTH_NAME_RE.match(text)
    if m and m.group(1).lower() in _MONTHS:
        return f"{int(m.group(2)):04d}-{_MONTHS[m.group(1).lower()]:02d}"
    # last resort: reuse full date parser then truncate
    iso = parse_date(text)
    return iso[:7] if iso else None


# ── Emails ──────────────────────────────────────────────────────────────────
def canonical_email(value: object) -> str | None:
    """Canonical email join key.

    Lowercase, trim, strip internal whitespace, repair the observed ``acmeinc``
    → ``acme-inc`` domain typo, and unify the underscore/dot separator
    convention (``patricia_lane`` ≡ ``patricia.lane``). Profiling showed this
    unification recovers ~522 real team members that would otherwise be false
    orphans, while fully resolving every team leader (see ASSUMPTIONS #3).
    """
    if value is None:
        return None
    text = normalize_whitespace(str(value)).lower().replace(" ", "")
    if text == "":
        return None
    text = text.replace("@acmeinc.com", "@acme-inc.com")
    # Unify separator convention in the local part (domains contain no '_').
    text = text.replace("_", ".")
    return text


def standardize_email_series(series: pd.Series) -> pd.Series:
    """Vectorised :func:`canonical_email`."""
    return series.map(canonical_email)


# ── Categoricals ────────────────────────────────────────────────────────────
def canonical_department(value: object) -> str | None:
    """Collapse casing variants of a department to Title-Case canonical form."""
    if value is None:
        return None
    text = normalize_whitespace(str(value))
    if text == "":
        return None
    # Preserve the ampersand form 'Data & Analytics', 'IT Operations' casing.
    special = {
        "it operations": "IT Operations",
        "data & analytics": "Data & Analytics",
        "human resources": "Human Resources",
        "customer success": "Customer Success",
    }
    return special.get(text.lower(), text.title())


# Every observed employment_type variant is a synonym for full-time / direct.
_EMPLOYMENT_TYPE_MAP = {
    "full-time": "Full-Time", "full time": "Full-Time", "ft": "Full-Time",
    "employee": "Full-Time", "fte": "Full-Time",
}


def canonical_employment_type(value: object) -> str | None:
    """Map employment_type variants to a single canonical label."""
    if value is None:
        return None
    text = normalize_whitespace(str(value)).lower()
    if text == "":
        return None
    return _EMPLOYMENT_TYPE_MAP.get(text, value.title() if isinstance(value, str) else value)


_TEAM_CODE_RE = re.compile(r"(?i)^tm[-_ ]?0*(\d+)$")


def canonical_team_code(value: object, width: int = 3) -> str | None:
    """Normalise team codes (`tm006`, `tm-5`, `TM 12`) to canonical `TM-###`.

    ``width`` sets zero-padding so `TM-006` matches `teams.team_id`.
    """
    if value is None:
        return None
    text = normalize_whitespace(str(value))
    m = _TEAM_CODE_RE.match(text)
    if not m:
        return text or None
    return f"TM-{int(m.group(1)):0{width}d}"


# ── Numerics ────────────────────────────────────────────────────────────────
def coerce_numeric(value: object) -> float | None:
    """Coerce to float, returning ``None`` for non-numeric (e.g. ``'Low'``)."""
    if value is None:
        return None
    text = normalize_whitespace(str(value))
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def bounded_int(value: object, lo: int, hi: int) -> tuple[int | None, bool]:
    """Coerce to int and enforce ``[lo, hi]``.

    Returns ``(value_or_None, is_valid)``. Out-of-range / non-numeric values
    return ``(None, False)`` so the pipeline can flag them without clamping.
    """
    num = coerce_numeric(value)
    if num is None:
        return None, False
    ivalue = int(round(num))
    if lo <= ivalue <= hi:
        return ivalue, True
    return None, False
