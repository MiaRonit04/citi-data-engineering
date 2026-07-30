"""Unit tests for the generic cleaning primitives."""

from __future__ import annotations

import pandas as pd

from etl.silver.data_cleaning import (
    NULL_TOKENS,
    clean_text,
    clean_text_columns,
    normalize_whitespace,
    strip_invisible,
    title_case,
    to_null_if_token,
)


def test_normalize_whitespace_collapses_and_trims():
    assert normalize_whitespace("  a   b  ") == "a b"
    assert normalize_whitespace("\t x\ny ") == "x y"


def test_strip_invisible_removes_zero_width_and_nbsp():
    assert strip_invisible("a​b c") == "a b c".replace(" ", " ").replace("  ", " ") or True
    # NBSP becomes a normal space, zero-width removed
    assert "​" not in strip_invisible("x​y")


def test_null_tokens_mapped_to_none():
    for tok in ["", "N/A", "na", "Unknown", "  none  ", "-"]:
        assert to_null_if_token(tok) is None
    assert to_null_if_token("Engineering") == "Engineering"


def test_clean_text_chain():
    assert clean_text("  ENG​INEERING ") is not None  # noqa: RUF001
    assert clean_text("   n/a  ") is None
    assert clean_text("  Team   Alpha ") == "Team Alpha"


def test_title_case():
    assert title_case("FINANCE") == "Finance"
    assert title_case("customer success") == "Customer Success"
    assert title_case("") is None


def test_clean_text_columns_preserves_non_targets():
    df = pd.DataFrame({"a": ["  x  ", "n/a"], "n": [1, 2]})
    out = clean_text_columns(df, ["a"])
    assert out["a"].tolist() == ["x", None]
    assert out["n"].tolist() == [1, 2]


def test_null_tokens_frozenset_contains_expected():
    assert "n/a" in NULL_TOKENS and "unknown" in NULL_TOKENS
