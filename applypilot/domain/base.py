import datetime
import re
from enum import StrEnum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TriState(StrEnum):
    """Three-valued logic state for recruitment facts."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PartialDate(_StrictModel):
    """Represents dates with optional month and day granularity."""

    year: int
    month: Optional[int] = None
    day: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def parse_from_string_or_date(cls, data: Any) -> Any:
        if isinstance(data, (datetime.date, datetime.datetime)):
            return {"year": data.year, "month": data.month, "day": data.day}
        if isinstance(data, str):
            match = re.fullmatch(
                r"(?P<year>\d{4})(?:-(?P<month>\d{1,2})(?:-(?P<day>\d{1,2}))?)?",
                data.strip(),
            )
            if match is not None:
                return {
                    key: int(value)
                    for key, value in match.groupdict().items()
                    if value is not None
                }
        return data

    @model_validator(mode="after")
    def validate_date_components(self) -> "PartialDate":
        if self.day is not None and self.month is None:
            raise ValueError("Cannot specify day without specifying month.")
        if self.month is not None and not (1 <= self.month <= 12):
            raise ValueError(f"Month must be between 1 and 12, got {self.month}")
        if self.day is not None and not (1 <= self.day <= 31):
            raise ValueError(f"Day must be between 1 and 31, got {self.day}")
        if self.day is not None:
            try:
                datetime.date(self.year, self.month, self.day)
            except ValueError as exc:
                raise ValueError(f"Invalid calendar date: {self.to_display()}") from exc
        return self

    def to_display(self) -> str:
        """Format date for display based on available precision."""
        if self.month is not None and self.day is not None:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.month is not None:
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


class FieldPolicy(_StrictModel):
    """Governance and masking policy for a specific field pattern."""

    path_pattern: str
    sensitivity: SensitivityLevel
    llm_allowed: bool
    log_strategy: LogStrategy = LogStrategy.MASK
    requires_confirmation: bool = False


class FactMetadata(_StrictModel):
    """Provenance and audit metadata for candidate facts."""

    source: str
    verified: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    updated_at: str
