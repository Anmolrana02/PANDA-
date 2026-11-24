"""The 29 audit fields: name, provider-level or location-level, and which Gold columns hold each one.

Every other file looks fields up here instead of typing field names itself.
The table follows docs/specs/01-contracts.md Part 2, in Audit Fields.txt order.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

__all__ = [
    "IGNORED_TRUST_FIELDS",
    "ComparisonMode",
    "Coverage",
    "FieldLevel",
    "FieldSpec",
    "UnknownField",
    "all_fields",
    "covered_fields",
    "get_field",
    "location_fields",
    "provider_fields",
]


class FieldLevel(StrEnum):
    """Whether a field belongs to the provider or to one practice location."""

    PROVIDER = "PROVIDER"
    LOCATION = "LOCATION"


class ComparisonMode(StrEnum):
    """How Gold and evidence values for a field are compared."""

    ONE_TO_ONE = "ONE_TO_ONE"
    SET = "SET"
    BY_LOCATION = "BY_LOCATION"


class Coverage(StrEnum):
    """Whether the trust matrix has source rows for a field yet."""

    COVERED = "COVERED"
    PENDING_MENTOR = "PENDING_MENTOR"


class FieldSpec(BaseModel):
    """One audit field. Frozen: nothing can change it while the program runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    level: FieldLevel
    mode: ComparisonMode
    gold_columns: tuple[str, ...]
    trust_fields: tuple[str, ...]
    coverage: Coverage

    @model_validator(mode="after")
    def _coverage_matches_trust_fields(self) -> Self:
        expected = Coverage.COVERED if self.trust_fields else Coverage.PENDING_MENTOR
        if self.coverage is not expected:
            raise ValueError(
                f"{self.name}: coverage must be {expected} when trust_fields is "
                f"{'set' if self.trust_fields else 'empty'}"
            )
        return self


class UnknownField(LookupError):
    """A field name that is not one of the 29 audit fields."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown audit field: {name!r}")
        self.name = name


# Trust-matrix names that belong to no audit field, left out on purpose.
IGNORED_TRUST_FIELDS: frozenset[str] = frozenset({"npi", "hospital_admitting_privileges"})

_PROVIDER = FieldLevel.PROVIDER
_LOCATION = FieldLevel.LOCATION
_ONE = ComparisonMode.ONE_TO_ONE
_SET = ComparisonMode.SET
_BY_LOC = ComparisonMode.BY_LOCATION

_ADDRESS = (
    "provider_address_line_1",
    "provider_address_line_2",
    "provider_city",
    "provider_state",
    "provider_zip",
)


def _spec(
    name: str,
    level: FieldLevel,
    mode: ComparisonMode,
    gold: tuple[str, ...],
    trust: tuple[str, ...] = (),
) -> FieldSpec:
    """Build one FieldSpec; coverage follows from whether it has trust-matrix names."""
    coverage = Coverage.COVERED if trust else Coverage.PENDING_MENTOR
    return FieldSpec(
        name=name,
        level=level,
        mode=mode,
        gold_columns=gold,
        trust_fields=trust,
        coverage=coverage,
    )


_FIELDS: tuple[FieldSpec, ...] = (
    _spec("npi_type", _PROVIDER, _ONE, ("npi_type",), ("npi_type",)),
    _spec(
        "provider_name",
        _PROVIDER,
        _ONE,
        ("first_name", "middle_name", "last_name"),
        ("first_name", "middle_name", "last_name"),
    ),
    _spec("provider_suffix", _PROVIDER, _ONE, ("suffix",), ("suffix",)),
    _spec("gender", _PROVIDER, _ONE, ("gender",), ("gender",)),
    _spec("degree", _PROVIDER, _ONE, ("degree",), ("degree",)),
    _spec("board_certifications", _PROVIDER, _ONE, ("board_certifications",)),
    _spec("medical_school", _PROVIDER, _ONE, ("provider_medical_school",)),
    _spec("accreditation_status", _PROVIDER, _ONE, ("accreditation_status",)),
    _spec(
        "specialty",
        _PROVIDER,
        _ONE,
        ("primary_specialty", "additional_specialties"),
        ("primary_speciality", "additional_specialities"),  # trust-matrix spelling
    ),
    _spec("role", _PROVIDER, _ONE, ("role",), ("role",)),
    _spec("practice_address", _LOCATION, _BY_LOC, _ADDRESS, _ADDRESS),
    _spec("practice_locations", _LOCATION, _SET, ("practice_location_id", *_ADDRESS), _ADDRESS),
    _spec("location_name", _LOCATION, _BY_LOC, ("location_name",), ("location_name",)),
    _spec("phone", _LOCATION, _BY_LOC, ("phone_number",), ("phone_number",)),
    _spec("website", _LOCATION, _BY_LOC, ("web_address",), ("web_address",)),
    _spec("office_hours", _LOCATION, _BY_LOC, ("office_hours",)),
    _spec("weekend_hours", _LOCATION, _BY_LOC, ("weekend_hours",)),
    _spec(
        "accepting_new_patients",
        _LOCATION,
        _BY_LOC,
        ("panel_status_accepting_new_patients",),
        ("panel_status_accepting_new_patients",),
    ),
    _spec("patient_age_restrictions", _LOCATION, _BY_LOC, ("patient_age_restrictions",)),
    _spec("languages", _PROVIDER, _ONE, ("provider_languages",)),
    _spec("office_languages", _LOCATION, _BY_LOC, ("office_languages",)),
    _spec("accommodations", _LOCATION, _BY_LOC, ("office_services_ada",)),
    _spec("interpreter_services", _LOCATION, _BY_LOC, ("office_services_interpreter",)),
    _spec("telehealth", _LOCATION, _BY_LOC, ("remote_service_type",)),
    _spec("network_participation", _PROVIDER, _ONE, ()),  # Gold column not decided yet
    _spec("license_status", _PROVIDER, _ONE, ()),
    _spec("license_number", _PROVIDER, _ONE, ()),
    _spec("expiration_date", _PROVIDER, _ONE, ()),
    _spec("practice_organization", _LOCATION, _BY_LOC, ("org_name",)),
)


def _index(fields: tuple[FieldSpec, ...]) -> Mapping[str, FieldSpec]:
    """Map name -> FieldSpec, refusing duplicate names."""
    by_name = {spec.name: spec for spec in fields}
    if len(by_name) != len(fields):
        raise ValueError("Duplicate field name in the field catalog")
    return MappingProxyType(by_name)


_BY_NAME = _index(_FIELDS)


def get_field(name: str) -> FieldSpec:
    """The FieldSpec for `name`, or UnknownField."""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise UnknownField(name) from None


def all_fields() -> tuple[FieldSpec, ...]:
    """All 29 fields in catalog order."""
    return _FIELDS


def provider_fields() -> tuple[FieldSpec, ...]:
    """Fields that belong to the provider."""
    return tuple(spec for spec in _FIELDS if spec.level is FieldLevel.PROVIDER)


def location_fields() -> tuple[FieldSpec, ...]:
    """Fields that belong to one practice location."""
    return tuple(spec for spec in _FIELDS if spec.level is FieldLevel.LOCATION)


def covered_fields() -> tuple[FieldSpec, ...]:
    """Fields that have trust-matrix rows."""
    return tuple(spec for spec in _FIELDS if spec.coverage is Coverage.COVERED)
