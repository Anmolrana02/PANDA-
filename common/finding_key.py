"""FindingKey = (field_name, representation, location_key): the unique id of one finding.

Reviewer decisions, field history and rationale are all stored under this key.
Rules: docs/specs/01-contracts.md Part 3.
"""

import json
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from common.field_catalog import FieldLevel, UnknownField, get_field

__all__ = ["PROVIDER_SCOPE", "REPORTED_ONLY_PREFIX", "FindingKey"]

PROVIDER_SCOPE: Final = "provider"
"""The location key of every provider-level field."""

REPORTED_ONLY_PREFIX: Final = "addr:"
"""Prefix of a location found only in evidence (no Gold practice_location_id)."""


class FindingKey(BaseModel):
    """Which field, in which representation, at which location. Frozen and hashable."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    field_name: str = Field(min_length=1)
    representation: str = Field(min_length=1)
    location_key: str = Field(min_length=1)

    def __init__(
        self, field_name: str, representation: str, location_key: str, **extra: object
    ) -> None:
        # Allows the spec's positional form. Extra keys go on to pydantic, which refuses them.
        super().__init__(
            field_name=field_name,
            representation=representation,
            location_key=location_key,
            **extra,
        )

    @model_validator(mode="after")
    def _scope_matches_field_level(self) -> Self:
        try:
            level = get_field(self.field_name).level
        except UnknownField:
            raise ValueError(f"unknown field: {self.field_name!r}") from None
        if level is FieldLevel.PROVIDER:
            if self.location_key != PROVIDER_SCOPE:
                raise ValueError(
                    f"{self.field_name} is a provider field; "
                    f"its location key must be {PROVIDER_SCOPE!r}"
                )
        elif self.location_key == PROVIDER_SCOPE:
            raise ValueError(
                f"{self.field_name} is a location field; "
                f"it cannot use location key {PROVIDER_SCOPE!r}"
            )
        elif self.location_key == REPORTED_ONLY_PREFIX:
            raise ValueError(f"empty address after {REPORTED_ONLY_PREFIX!r}")
        return self

    @classmethod
    def for_provider(cls, field_name: str, representation: str) -> Self:
        """Key for a provider-level field."""
        return cls(field_name, representation, PROVIDER_SCOPE)

    @classmethod
    def for_location(cls, field_name: str, representation: str, location_key: str) -> Self:
        """Key for a location-level field at one Gold or reported-only location."""
        return cls(field_name, representation, location_key)

    def row_id(self) -> str:
        """'<field_name>:<location_key>', the validation row id format."""
        return f"{self.field_name}:{self.location_key}"

    def is_provider_scope(self) -> bool:
        """True for a provider-level key."""
        return self.location_key == PROVIDER_SCOPE

    def is_reported_only(self) -> bool:
        """True for a location found only in evidence."""
        return self.location_key.startswith(REPORTED_ONLY_PREFIX)

    def to_str(self) -> str:
        """A JSON list of the three parts, for URLs and database columns."""
        parts = [self.field_name, self.representation, self.location_key]
        return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_str(cls, text: str) -> Self:
        """Rebuild a key from to_str() output. Raises ValueError on anything else."""
        try:
            parts = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"not a finding key: {text!r}") from exc
        if not isinstance(parts, list) or len(parts) != 3:
            raise ValueError(f"finding key must be a JSON list of 3 parts: {text!r}")
        if not all(isinstance(part, str) for part in parts):
            raise ValueError(f"finding key parts must all be text: {text!r}")
        field_name, representation, location_key = parts
        return cls(field_name, representation, location_key)
