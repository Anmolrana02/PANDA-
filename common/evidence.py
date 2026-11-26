"""Evidence Assertion (what one source said about one field) and Evidence Bundle.

Every source adapter returns these shapes, so the validator can compare any
source with Gold and every value traces back to its source, URL and time.
They hold facts only: no match result, score or route.
Rules: docs/specs/01-contracts-02.md Part 4.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from common.field_catalog import FieldLevel, UnknownField, get_field

__all__ = [
    "MAX_RAW_VALUE_LENGTH",
    "AssertionStatus",
    "DataGroup",
    "EvidenceAssertion",
    "EvidenceBundle",
    "LocationRef",
    "QualityLabel",
    "SourceId",
]

MAX_RAW_VALUE_LENGTH = 2000
"""A raw value longer than this is refused: a whole web page is never a value."""

NonEmptyStr = Annotated[str, Field(min_length=1)]
Npi = Annotated[str, Field(pattern=r"^\d{10}$")]


class SourceId(StrEnum):
    """An approved evidence source."""

    CAQH = "caqh"
    NPPES = "nppes"
    PROVIDER_WEBSITE = "provider_website"
    GOOGLE_SEARCH = "google_search"

    @property
    def trust_matrix_name(self) -> str:
        """The source's name in the trust matrix's source_system column."""
        return _TRUST_MATRIX_NAMES[self]


_TRUST_MATRIX_NAMES: Mapping[SourceId, str] = MappingProxyType(
    {
        SourceId.CAQH: "CAQH",
        SourceId.NPPES: "NPPES",
        SourceId.PROVIDER_WEBSITE: "Provider Website",
        SourceId.GOOGLE_SEARCH: "Google Searches",
    }
)


class DataGroup(StrEnum):
    """Which group of fields a source call was about."""

    IDENTITY = "IDENTITY"
    ATTESTATION = "ATTESTATION"
    LOCATION = "LOCATION"


class AssertionStatus(StrEnum):
    """What happened when the source was asked for one field."""

    FOUND = "FOUND"
    NO_VALUE = "NO_VALUE"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"


class QualityLabel(StrEnum):
    """Whether the source said the value directly or we reshaped it."""

    STATED = "STATED"
    TRANSFORMED = "TRANSFORMED"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


class LocationRef(_Frozen):
    """The office a location-field assertion is about, as the source described it."""

    display_address: NonEmptyStr
    location_name: str | None = None
    practice_location_id: str | None = None


class EvidenceAssertion(_Frozen):
    """One fact: one field, from one source, and for location fields one office."""

    case_id: NonEmptyStr
    npi: Npi
    field_name: str
    data_group: DataGroup
    source_id: SourceId
    raw_value: Annotated[str, Field(max_length=MAX_RAW_VALUE_LENGTH)] | None
    normalized_value: str | None = None
    status: AssertionStatus
    status_detail: str | None = None
    url_or_identifier: NonEmptyStr
    retrieved_at: AwareDatetime
    source_last_update: date | None = None
    quality_label: QualityLabel
    adapter_version: NonEmptyStr
    location_ref: LocationRef | None = None

    @field_validator("retrieved_at")
    @classmethod
    def _retrieved_at_in_utc(cls, value: datetime) -> datetime:
        return _to_utc(value)

    @model_validator(mode="after")
    def _check_value_and_office(self) -> Self:
        try:
            level = get_field(self.field_name).level
        except UnknownField:
            raise ValueError(f"unknown field: {self.field_name!r}") from None
        if self.status is AssertionStatus.FOUND:
            if not self.raw_value:
                raise ValueError("status FOUND needs a non-empty raw_value")
        elif self.raw_value is not None or self.normalized_value is not None:
            raise ValueError(f"status {self.status}: no value allowed")
        if level is FieldLevel.PROVIDER and self.location_ref is not None:
            raise ValueError(f"{self.field_name}: provider field has no office (location_ref)")
        if (
            level is FieldLevel.LOCATION
            and self.status is AssertionStatus.FOUND
            and self.location_ref is None
        ):
            raise ValueError(f"{self.field_name}: location field needs an office (location_ref)")
        return self


class EvidenceBundle(_Frozen):
    """All assertions from one source and one data group for one case, in order."""

    case_id: NonEmptyStr
    npi: Npi
    source_id: SourceId
    data_group: DataGroup
    gold_version: NonEmptyStr
    trust_matrix_version: NonEmptyStr
    correlation_id: NonEmptyStr
    created_at: AwareDatetime
    assertions: Annotated[tuple[EvidenceAssertion, ...], Field(min_length=1)]

    @field_validator("created_at")
    @classmethod
    def _created_at_in_utc(cls, value: datetime) -> datetime:
        return _to_utc(value)

    @model_validator(mode="after")
    def _assertions_match_bundle(self) -> Self:
        for index, item in enumerate(self.assertions):
            if item.source_id is not self.source_id:
                raise ValueError(
                    f"mixed sources: assertion {index} is {item.source_id}, "
                    f"bundle is {self.source_id}"
                )
            for name in ("case_id", "npi", "data_group"):
                if getattr(item, name) != getattr(self, name):
                    raise ValueError(f"assertion {index} has a different {name} from the bundle")
        return self
