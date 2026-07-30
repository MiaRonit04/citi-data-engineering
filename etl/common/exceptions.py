"""Typed exception hierarchy for the ETL platform.

A narrow, well-named hierarchy lets callers distinguish *recoverable* problems
(one dataset failed — keep going) from *fatal* ones (config missing — stop).
"""

from __future__ import annotations


class ETLError(Exception):
    """Base class for every pipeline error."""


class ConfigurationError(ETLError):
    """Raised when configuration is missing or invalid — fatal."""


class IngestionError(ETLError):
    """Raised when a single dataset cannot be ingested — recoverable per-dataset."""


class SchemaValidationError(ETLError):
    """Raised when a dataset fails schema validation."""


class RelationshipValidationError(ETLError):
    """Raised when referential-integrity checks fail hard."""


class TransientError(ETLError):
    """A transient failure (e.g. network / DB blip) that is worth retrying."""


class GoldValidationError(ETLError):
    """Raised when a Gold dataset fails its post-build validation contract."""
