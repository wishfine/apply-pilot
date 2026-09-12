from enum import StrEnum
from typing import Optional
from pydantic import BaseModel, Field


class TriState(StrEnum):
    """Three-valued logic state for recruitment facts."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class PartialDate(BaseModel):
    """Represents dates with optional month and day granularity."""

    year: int
    month: Optional[int] = None
    day: Optional[int] = None

    def to_display(self) -> str:
        """Format date for display based on available precision."""
        if self.month and self.day:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.month:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"

    def __str__(self) -> str:
        return self.to_display()


class SensitivityLevel(StrEnum):
    """Data sensitivity classification."""

    PUBLIC = "public"
    NORMAL = "normal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class LogStrategy(StrEnum):
    """Log sanitization strategy."""

    PLAIN = "plain"
    MASK = "mask"
    OMIT = "omit"


class FieldPolicy(BaseModel):
    """Governance and masking policy for a specific field pattern."""

    path_pattern: str
    sensitivity: SensitivityLevel
    llm_allowed: bool
    log_strategy: LogStrategy = LogStrategy.MASK
    requires_confirmation: bool = False


class FactMetadata(BaseModel):
    """Provenance and audit metadata for candidate facts."""

    source: str
    verified: bool = False
    confidence: float = 1.0
    updated_at: str
