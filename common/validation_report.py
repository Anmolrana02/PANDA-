"""Schema-7 Validation Report: the contract between the agent (writes it) and the portal (reads it).

The portal builds the review screen only from this report, so the report
refuses anything ambiguous instead of guessing. Every error names the entry
and the rule, and nothing is skipped or repaired.
Rules: docs/specs/01-contracts-02.md Part 6.
"""

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal, NoReturn, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from common.evidence import DataGroup, NonEmptyStr, Npi, QualityLabel, SourceId
from common.field_catalog import ComparisonMode, UnknownField, get_field
from common.finding_key import PROVIDER_SCOPE, REPORTED_ONLY_PREFIX, FindingKey

__all__ = [
    "ALLOWED_REASONS",
    "CONFIDENCE_FACTORS",
    "SCHEMA_VERSION",
    "ComparisonType",
    "Confidence",
    "ConflictRef",
    "EvidenceLocationRef",
    "LocationContext",
    "ReasonCode",
    "SourceSummary",
    "ValidationEntry",
    "ValidationReport",
    "ValidationRow",
    "ValidationStatus",
]

SCHEMA_VERSION: Final = 7
CONFIDENCE_FACTORS: frozenset[str] = frozenset(
    {"authority", "recency", "quality", "reliability", "corroboration"}
)
_TOTAL_KEYS: Final = ("total_validations", "total_conflicts", "conflicts")


class ValidationStatus(StrEnum):
    """The outcome of one comparison, or of a whole field."""

    CONFIRMED = "CONFIRMED"
    DISCREPANCY = "DISCREPANCY"
    CANNOT_BE_VERIFIED = "CANNOT_BE_VERIFIED"
    FATAL_FLAW = "FATAL_FLAW"


class ComparisonType(StrEnum):
    """What the comparison of Gold and evidence found."""

    MATCHED = "MATCHED"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    MISSING_VALUE = "MISSING_VALUE"
    ONLY_IN_GOLD = "ONLY_IN_GOLD"
    ONLY_IN_EVIDENCE = "ONLY_IN_EVIDENCE"


class ReasonCode(StrEnum):
    """Why a row has its status."""

    VALUE_MATCH = "VALUE_MATCH"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    NEW_EVIDENCE_VALUE = "NEW_EVIDENCE_VALUE"
    MISSING_DIRECTORY_VALUE = "MISSING_DIRECTORY_VALUE"
    MISSING_EVIDENCE_VALUE = "MISSING_EVIDENCE_VALUE"
    NO_VALUE = "NO_VALUE"
    NOT_REPORTED_FOR_LOCATION = "NOT_REPORTED_FOR_LOCATION"
    NOT_CORROBORATED = "NOT_CORROBORATED"


_R = ReasonCode
ALLOWED_REASONS: Mapping[ValidationStatus, frozenset[ReasonCode]] = MappingProxyType(
    {
        ValidationStatus.CONFIRMED: frozenset({_R.VALUE_MATCH}),
        ValidationStatus.DISCREPANCY: frozenset(
            {_R.VALUE_MISMATCH, _R.NEW_EVIDENCE_VALUE, _R.MISSING_DIRECTORY_VALUE}
        ),
        ValidationStatus.CANNOT_BE_VERIFIED: frozenset(
            {
                _R.NO_VALUE,
                _R.MISSING_EVIDENCE_VALUE,
                _R.NOT_REPORTED_FOR_LOCATION,
                _R.NOT_CORROBORATED,
            }
        ),
        ValidationStatus.FATAL_FLAW: frozenset(ReasonCode),  # a safety flag, any reason
    }
)
"""Which reason codes each status allows (spec table)."""

_CONFLICT_STATUSES: Final = frozenset({ValidationStatus.DISCREPANCY, ValidationStatus.FATAL_FLAW})


class _Frozen(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


def _read_only(value: Mapping[str, float] | None) -> Mapping[str, float] | None:
    return None if value is None else MappingProxyType(dict(value))


def _plain(value: Mapping[str, float] | None) -> dict[str, float] | None:
    return None if value is None else dict(value)


class LocationContext(_Frozen):
    """How an office is shown to the reviewer. Display only; never part of a key."""

    display_address: NonEmptyStr
    location_name: str | None = None
    practice_location_id: str | None = None


class EvidenceLocationRef(_Frozen):
    """A source's own id for an office (spec name: LocationRef)."""

    source_id: SourceId
    source_location_id: NonEmptyStr


class Confidence(_Frozen):
    """A row's own score. Never copied from another row or from the case."""

    scored: bool
    score: float | None = None
    action: str  # plain text until the mentor picks one action vocabulary
    factors: Mapping[str, float] | None = None
    penalties: Mapping[str, float] | None = None

    @field_validator("factors", "penalties")
    @classmethod
    def _freeze(cls, value: Mapping[str, float] | None) -> Mapping[str, float] | None:
        return _read_only(value)

    @field_serializer("factors", "penalties")
    def _as_dict(self, value: Mapping[str, float] | None) -> dict[str, float] | None:
        return _plain(value)

    @model_validator(mode="after")
    def _check_score(self) -> Self:
        if self.scored:
            if self.score is None or not 0 <= self.score <= 1:
                raise ValueError("rule 15: scored confidence needs 0 <= score <= 1")
        elif self.score is not None:
            raise ValueError("rule 15: unscored confidence must have score None")
        if self.factors is not None:
            if set(self.factors) != CONFIDENCE_FACTORS:
                raise ValueError(f"rule 16: factors must be exactly {sorted(CONFIDENCE_FACTORS)}")
            for name, value in self.factors.items():
                if not 0 <= value <= 1:
                    raise ValueError(f"rule 16: factor {name!r} must be between 0 and 1")
        return self


class SourceSummary(_Frozen):
    """What one source said, as shown to the reviewer."""

    source_id: SourceId
    value: str | None = None
    url: NonEmptyStr
    data_group: DataGroup
    quality_label: QualityLabel
    source_last_update: date | None = None
    retrieved_at: AwareDatetime
    matches_directory: bool | None = None
    status_detail: str | None = None

    @field_validator("retrieved_at")
    @classmethod
    def _in_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class ValidationRow(_Frozen):
    """One comparison. Checked against its entry by ValidationEntry."""

    validation_row_id: NonEmptyStr
    location_group_id: str | None = None
    directory_location_id: str | None = None
    location_context: LocationContext | None = None
    evidence_location_refs: tuple[EvidenceLocationRef, ...] = ()
    comparison_type: ComparisonType
    gold_value: str | None = None
    evidence_value: str | None = None
    recommended_value: str | None = None
    validation_status: ValidationStatus
    reason_code: ReasonCode
    evidence_sources: tuple[SourceId, ...] = ()
    confidence: Confidence


class ConflictRef(_Frozen):
    """Points at an entry whose status is DISCREPANCY or FATAL_FLAW."""

    field: str
    representation: str


class ValidationEntry(_Frozen):
    """One field in one representation."""

    schema_version: Literal[7] = Field(default=SCHEMA_VERSION, alias="schema")
    field: str
    representation: NonEmptyStr
    comparison_mode: ComparisonMode
    data_group: DataGroup
    status: ValidationStatus
    rationale: str
    sources: tuple[SourceSummary, ...]
    validation_rows: Annotated[tuple[ValidationRow, ...], Field(min_length=1)]

    @property
    def label(self) -> str:
        """'<field>/<representation>', used in every error message."""
        return f"{self.field}/{self.representation}"

    def _fail(self, rule: int, message: str) -> NoReturn:
        raise ValueError(f"entry {self.label}: rule {rule}: {message}")

    @model_validator(mode="after")
    def _check_entry(self) -> Self:
        try:
            expected_mode = get_field(self.field).mode
        except UnknownField:
            self._fail(4, f"unknown field {self.field!r}")
        if self.comparison_mode is not expected_mode:
            if self.comparison_mode is ComparisonMode.SET:
                self._fail(5, "only practice_locations may be SET")
            self._fail(5, f"mode must be {expected_mode}")
        if expected_mode is ComparisonMode.ONE_TO_ONE and len(self.validation_rows) != 1:
            self._fail(8, "ONE_TO_ONE needs exactly one row")
        ids = Counter(row.validation_row_id for row in self.validation_rows)
        if repeated := [row_id for row_id, count in ids.items() if count > 1]:
            self._fail(6, f"validation_row_id repeated: {repeated}")
        cited = {summary.source_id for summary in self.sources}
        for row in self.validation_rows:
            self._check_row(row, cited)
        return self

    def _check_row(self, row: ValidationRow, cited: set[SourceId]) -> None:
        row_label = f"row {row.validation_row_id!r}"
        if missing := [s.value for s in row.evidence_sources if s not in cited]:
            self._fail(7, f"{row_label} cites sources not in the entry's sources: {missing}")
        if self.comparison_mode is ComparisonMode.ONE_TO_ONE:
            self._check_provider_row(row, row_label)
        else:
            self._check_location_row(row, row_label)
        if row.reason_code not in ALLOWED_REASONS[row.validation_status]:
            self._fail(
                13,
                f"{row_label}: reason {row.reason_code} is not allowed for {row.validation_status}",
            )
        status = row.validation_status
        if status is ValidationStatus.CANNOT_BE_VERIFIED and row.recommended_value is not None:
            self._fail(14, f"{row_label}: CANNOT_BE_VERIFIED must have no recommended_value")
        if status is ValidationStatus.DISCREPANCY and not row.recommended_value:
            self._fail(14, f"{row_label}: DISCREPANCY needs a recommended_value")
        self._key_for(row, row_label)

    def _check_provider_row(self, row: ValidationRow, row_label: str) -> None:
        if (
            row.location_group_id is not None
            or row.directory_location_id is not None
            or row.location_context is not None
        ):
            self._fail(8, f"{row_label}: ONE_TO_ONE row has no location fields")
        expected = f"{self.field}:{PROVIDER_SCOPE}"
        if row.validation_row_id != expected:
            self._fail(8, f"{row_label} must be {expected!r}")

    def _check_location_row(self, row: ValidationRow, row_label: str) -> None:
        group = row.location_group_id
        if group is None:
            self._fail(11, f"{row_label} needs a location_group_id")
        expected = f"{self.field}:{group}"
        if row.validation_row_id != expected:
            self._fail(11, f"{row_label} must be {expected!r}")
        if group.startswith(REPORTED_ONLY_PREFIX):
            if row.directory_location_id is not None:
                self._fail(12, f"{row_label}: an 'addr:' row has no directory_location_id")
        elif row.directory_location_id != group:
            self._fail(12, f"{row_label}: directory_location_id must equal location_group_id")

    def _key_for(self, row: ValidationRow, row_label: str) -> FindingKey:
        location = row.location_group_id or PROVIDER_SCOPE
        try:
            return FindingKey(self.field, self.representation, location)
        except ValidationError as exc:
            reason = exc.errors()[0]["msg"]
            self._fail(17, f"{row_label}: cannot build a finding key: {reason}")

    def finding_keys(self) -> tuple[FindingKey, ...]:
        """One FindingKey per row, in row order."""
        return tuple(self._key_for(row, row.validation_row_id) for row in self.validation_rows)


class ValidationReport(_Frozen):
    """The schema-7 report for one case. Totals are always worked out from the entries."""

    report_id: NonEmptyStr
    case_id: NonEmptyStr
    practitioner_npi: Npi
    validated_at: AwareDatetime
    gold_version: NonEmptyStr
    trust_matrix_version: NonEmptyStr
    validations: tuple[ValidationEntry, ...]

    @field_validator("validated_at")
    @classmethod
    def _in_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_validations(self) -> int:
        """Number of entries."""
        return len(self.validations)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def conflicts(self) -> tuple[ConflictRef, ...]:
        """Entries whose status is DISCREPANCY or FATAL_FLAW, in report order."""
        return tuple(
            ConflictRef(field=entry.field, representation=entry.representation)
            for entry in self.validations
            if entry.status in _CONFLICT_STATUSES
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_conflicts(self) -> int:
        """Number of conflicts."""
        return len(self.conflicts)

    @model_validator(mode="wrap")
    @classmethod
    def _given_totals_must_match(cls, data: Any, handler: Callable[[Any], Self]) -> Self:
        given: dict[str, Any] = {}
        if isinstance(data, Mapping):
            data = dict(data)
            given = {key: data.pop(key) for key in _TOTAL_KEYS if key in data}
        report = handler(data)
        for key, value in given.items():
            computed = getattr(report, key)
            if key == "conflicts":
                value = tuple(ConflictRef.model_validate(item) for item in value)
            if value != computed:
                raise ValueError(f"rule 3: {key} is worked out from the entries ({computed!r})")
        return report

    @model_validator(mode="after")
    def _check_report(self) -> Self:
        pairs = Counter((entry.field, entry.representation) for entry in self.validations)
        if repeated := [f"{f}/{r}" for (f, r), count in pairs.items() if count > 1]:
            raise ValueError(f"rule 2: duplicate entry: {repeated}")
        self._check_locations()
        return self

    def _check_locations(self) -> None:
        set_entries: dict[str, ValidationEntry] = {}
        has_set = {
            e.representation for e in self.validations if e.comparison_mode is ComparisonMode.SET
        }
        for entry in self.validations:
            rep = entry.representation
            if entry.comparison_mode is ComparisonMode.SET:
                set_entries[rep] = entry
            elif entry.comparison_mode is ComparisonMode.BY_LOCATION:
                set_entry = set_entries.get(rep)
                if set_entry is None:
                    problem = (
                        "SET must come first"
                        if rep in has_set
                        else "needs a practice_locations SET entry"
                    )
                    raise ValueError(f"entry {entry.label}: rule 9: {problem}")
                self._check_against_set(entry, set_entry)

    @staticmethod
    def _check_against_set(entry: ValidationEntry, set_entry: ValidationEntry) -> None:
        contexts = {
            row.location_group_id: row.location_context for row in set_entry.validation_rows
        }
        for row in entry.validation_rows:
            if row.location_group_id not in contexts:
                raise ValueError(
                    f"entry {entry.label}: rule 10: location group {row.location_group_id!r} "
                    f"is not in {set_entry.label}"
                )
            if row.location_context != contexts[row.location_group_id]:
                raise ValueError(
                    f"entry {entry.label}: rule 10: location_context for "
                    f"{row.location_group_id!r} differs from {set_entry.label}"
                )

    def finding_keys(self) -> tuple[FindingKey, ...]:
        """One FindingKey per row, in report order (rule 17)."""
        return tuple(key for entry in self.validations for key in entry.finding_keys())
