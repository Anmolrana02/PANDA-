"""Tests that every contract validates good examples and rejects bad ones, including a sample report."""

import json
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from common.evidence import (
    AssertionStatus,
    DataGroup,
    EvidenceAssertion,
    EvidenceBundle,
    LocationRef,
    QualityLabel,
    SourceId,
)
from common.field_catalog import (
    IGNORED_TRUST_FIELDS,
    ComparisonMode,
    Coverage,
    FieldLevel,
    FieldSpec,
    UnknownField,
    all_fields,
    covered_fields,
    get_field,
    location_fields,
    provider_fields,
)
from common.finding_key import PROVIDER_SCOPE, FindingKey
from common.search_plan import (
    CaseType,
    SearchPlan,
    SkippedSource,
    SkipReason,
    SourceTask,
    TaskOrigin,
    UnplannedField,
    UnplannedReason,
)
from common.states import (
    AGENT_CASE_MOVES,
    DISPATCH_MOVES,
    PORTAL_BATCH_MOVES,
    AgentCaseState,
    DispatchState,
    InvalidTransition,
    PortalBatchState,
    allowed_moves,
    can_transition,
    is_final,
    require_transition,
)

# --- Part 1: states (docs/specs/01-contracts.md) ---

A = AgentCaseState
D = DispatchState
P = PortalBatchState

AGENT_FINALS = {A.CLOSED, A.HITL_PENDING, A.CANCELLED}


# Acceptance cases 1-8: agent case moves


def test_01_agent_created_to_planned_allowed() -> None:
    assert can_transition(A.CREATED, A.PLANNED)


def test_02_agent_created_to_scoring_refused() -> None:
    assert not can_transition(A.CREATED, A.SCORING)


@pytest.mark.parametrize("target", [A.CLOSED, A.HITL_PENDING])
def test_03_agent_routing_to_closed_or_hitl_allowed(target: AgentCaseState) -> None:
    assert can_transition(A.ROUTING, target)


def test_04_agent_validating_to_cancelled_allowed() -> None:
    assert can_transition(A.VALIDATING, A.CANCELLED)


@pytest.mark.parametrize("target", list(AgentCaseState))
def test_05_agent_closed_to_anything_refused(target: AgentCaseState) -> None:
    assert not can_transition(A.CLOSED, target)


def test_06_agent_cancelled_to_cancelled_refused() -> None:
    assert not can_transition(A.CANCELLED, A.CANCELLED)


def test_07_agent_same_status_refused() -> None:
    assert not can_transition(A.SCORING, A.SCORING)


def test_08_agent_no_going_back() -> None:
    assert not can_transition(A.SCORING, A.PLANNED)


# Acceptance case 9: final statuses


@pytest.mark.parametrize("state", list(AgentCaseState))
def test_09_agent_is_final(state: AgentCaseState) -> None:
    assert is_final(state) == (state in AGENT_FINALS)


# Acceptance cases 10-12: dispatch job


def test_10_dispatch_retry_allowed() -> None:
    assert can_transition(D.DISPATCHING, D.PENDING)


def test_11_dispatch_exhausted_is_final() -> None:
    assert not can_transition(D.EXHAUSTED, D.PENDING)


def test_12_dispatch_must_dispatch_first() -> None:
    assert not can_transition(D.PENDING, D.DONE)


# Acceptance cases 13-14: portal batch


@pytest.mark.parametrize("target", [P.EXPERT_REVIEW, P.CLOSED])
def test_13_portal_reviewer_decided_moves(target: PortalBatchState) -> None:
    assert can_transition(P.REVIEWER_DECIDED, target)


def test_14_portal_in_progress_to_closed_refused() -> None:
    assert not can_transition(P.IN_PROGRESS, P.CLOSED)


# Acceptance case 15: error names both statuses


def test_15_require_transition_raises_with_both_statuses() -> None:
    with pytest.raises(
        InvalidTransition, match="^Cannot move agent case from CREATED to SCORING$"
    ) as excinfo:
        require_transition(A.CREATED, A.SCORING)
    assert excinfo.value.current is A.CREATED
    assert excinfo.value.proposed is A.SCORING


def test_15b_require_transition_allowed_does_not_raise() -> None:
    require_transition(A.CREATED, A.PLANNED)  # no exception


# Acceptance case 16: statuses save as plain text


def test_16_state_serializes_as_plain_text() -> None:
    assert json.dumps(A.SCORING) == '"SCORING"'
    assert str(A.SCORING) == "SCORING"


@pytest.mark.parametrize("state", [*AgentCaseState, *DispatchState, *PortalBatchState])
def test_16b_every_value_is_its_upper_case_name(state: str) -> None:
    assert isinstance(state, AgentCaseState | DispatchState | PortalBatchState)
    assert state.value == state.name


# Acceptance case 17: every status has a table entry


@pytest.mark.parametrize(
    ("enum", "table"),
    [
        (AgentCaseState, AGENT_CASE_MOVES),
        (DispatchState, DISPATCH_MOVES),
        (PortalBatchState, PORTAL_BATCH_MOVES),
    ],
)
def test_17_every_status_has_an_entry(enum: type, table: object) -> None:
    assert set(table) == set(enum)  # type: ignore[call-overload]


# Extra rule tests (rules 3-7)


@pytest.mark.parametrize(
    ("enum", "table"),
    [
        (AgentCaseState, AGENT_CASE_MOVES),
        (DispatchState, DISPATCH_MOVES),
        (PortalBatchState, PORTAL_BATCH_MOVES),
    ],
)
def test_table_targets_belong_to_same_machine(enum: type, table: object) -> None:
    for targets in table.values():  # type: ignore[attr-defined]
        for target in targets:
            assert type(target) is enum


@pytest.mark.parametrize("state", list(AgentCaseState))
def test_rule4_cancelled_reachable_only_from_non_final(state: AgentCaseState) -> None:
    assert can_transition(state, A.CANCELLED) == (state not in AGENT_FINALS)


@pytest.mark.parametrize("state", [*AgentCaseState, *DispatchState, *PortalBatchState])
def test_rule2_same_status_always_refused(state: AgentCaseState) -> None:
    assert not can_transition(state, state)


@pytest.mark.parametrize(
    ("state", "final"),
    [
        (D.PENDING, False),
        (D.DISPATCHING, False),
        (D.DONE, True),
        (D.EXHAUSTED, True),
        (P.EXPERT_REVIEW, False),
        (P.CLOSED, True),
    ],
)
def test_rule3_dispatch_and_portal_finals(state: AgentCaseState, final: bool) -> None:
    assert is_final(state) == final
    if final:
        assert allowed_moves(state) == frozenset()


def test_rule5_machines_cannot_be_mixed() -> None:
    # StrEnum members equal plain strings, so A.CLOSED == P.CLOSED is True.
    # The check must still refuse a cross-machine move.
    with pytest.raises(TypeError):
        can_transition(A.ROUTING, P.CLOSED)  # type: ignore[type-var]
    with pytest.raises(TypeError):
        require_transition(D.PENDING, A.PLANNED)  # type: ignore[type-var]


def test_rule5_plain_strings_rejected() -> None:
    with pytest.raises(TypeError):
        can_transition("CREATED", "PLANNED")  # type: ignore[type-var]


@pytest.mark.parametrize(
    ("current", "proposed", "message"),
    [
        (D.PENDING, D.DONE, "Cannot move dispatch job from PENDING to DONE"),
        (P.IN_PROGRESS, P.CLOSED, "Cannot move portal batch from IN_PROGRESS to CLOSED"),
    ],
)
def test_rule7_error_labels(
    current: AgentCaseState, proposed: AgentCaseState, message: str
) -> None:
    with pytest.raises(InvalidTransition, match=f"^{message}$"):
        require_transition(current, proposed)


def test_rule6_tables_are_read_only() -> None:
    with pytest.raises(TypeError):
        AGENT_CASE_MOVES[A.CREATED] = frozenset()  # type: ignore[index]


# --- Part 2: field catalog (docs/specs/01-contracts.md) ---

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
NO_GOLD_COLUMN = {"network_participation", "license_status", "license_number", "expiration_date"}


def _lines(path: Path) -> list[str]:
    """Non-blank, stripped lines of a text file."""
    return [
        line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()
    ]


def _catalog_trust_names() -> set[str]:
    return {name for spec in all_fields() for name in spec.trust_fields}


def test_c01_catalog_has_29_fields() -> None:
    assert len(all_fields()) == 29


def test_c02_names_and_order_match_audit_fields_txt() -> None:
    expected = _lines(REPO_ROOT / "data_plane" / "seed" / "Audit Fields.txt")
    assert [spec.name for spec in all_fields()] == expected


def test_c03_thirteen_covered_fields() -> None:
    assert len(covered_fields()) == 13
    assert all(spec.coverage is Coverage.COVERED for spec in covered_fields())


def test_c04_only_practice_locations_uses_set() -> None:
    assert [s.name for s in all_fields() if s.mode is ComparisonMode.SET] == ["practice_locations"]


def test_c05_phone() -> None:
    spec = get_field("phone")
    assert spec.level is FieldLevel.LOCATION
    assert spec.mode is ComparisonMode.BY_LOCATION
    assert spec.gold_columns == ("phone_number",)
    assert spec.coverage is Coverage.COVERED


def test_c06_specialty_trust_names_use_trust_spelling() -> None:
    assert get_field("specialty").trust_fields == (
        "primary_speciality",
        "additional_specialities",
    )


def test_c07_office_hours_pending_mentor() -> None:
    spec = get_field("office_hours")
    assert spec.trust_fields == ()
    assert spec.coverage is Coverage.PENDING_MENTOR


def test_c08_license_number_has_no_gold_column() -> None:
    assert get_field("license_number").gold_columns == ()


def test_c09_unknown_field_names_it() -> None:
    with pytest.raises(UnknownField, match="'fax'"):
        get_field("fax")


def test_c10_every_gold_column_is_real() -> None:
    real = set(_lines(FIXTURES / "gold_columns.txt"))
    used = {col for spec in all_fields() for col in spec.gold_columns}
    assert used - real == set()


def test_c11_every_trust_name_is_real() -> None:
    real = set(_lines(FIXTURES / "trust_field_names.txt"))
    assert _catalog_trust_names() - real == set()


def test_c12_field_spec_is_frozen() -> None:
    spec = get_field("phone")
    with pytest.raises(ValidationError):
        spec.level = FieldLevel.PROVIDER


def test_c13_provider_and_location_fields_partition_catalog() -> None:
    provider = {s.name for s in provider_fields()}
    location = {s.name for s in location_fields()}
    assert provider & location == set()
    assert provider | location == {s.name for s in all_fields()}
    assert len(provider) + len(location) == 29


@pytest.mark.parametrize("spec", all_fields(), ids=lambda s: s.name)
def test_c14_coverage_matches_trust_fields(spec: FieldSpec) -> None:
    expected = Coverage.COVERED if spec.trust_fields else Coverage.PENDING_MENTOR
    assert spec.coverage is expected


def test_c15_ignored_plus_catalog_cover_all_trust_names() -> None:
    real = set(_lines(FIXTURES / "trust_field_names.txt"))
    assert len(real) == 21
    assert IGNORED_TRUST_FIELDS.isdisjoint(_catalog_trust_names())
    assert IGNORED_TRUST_FIELDS | _catalog_trust_names() == real


# Extra rule tests (rules 2, 5, 8, 9)


def test_rule2_names_unique() -> None:
    names = [s.name for s in all_fields()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("spec", all_fields(), ids=lambda s: s.name)
def test_rule5_mode_follows_level(spec: FieldSpec) -> None:
    if spec.level is FieldLevel.PROVIDER:
        assert spec.mode is ComparisonMode.ONE_TO_ONE
    elif spec.name != "practice_locations":
        assert spec.mode is ComparisonMode.BY_LOCATION


def test_rule9_only_four_fields_lack_gold_columns() -> None:
    assert {s.name for s in all_fields() if not s.gold_columns} == NO_GOLD_COLUMN


@pytest.mark.parametrize(
    ("trust_fields", "coverage"),
    [(("phone_number",), Coverage.PENDING_MENTOR), ((), Coverage.COVERED)],
)
def test_rule8_model_rejects_wrong_coverage(
    trust_fields: tuple[str, ...], coverage: Coverage
) -> None:
    with pytest.raises(ValidationError):
        FieldSpec(
            name="x",
            level=FieldLevel.LOCATION,
            mode=ComparisonMode.BY_LOCATION,
            gold_columns=("x",),
            trust_fields=trust_fields,
            coverage=coverage,
        )


def test_field_spec_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        FieldSpec.model_validate(
            {
                "name": "x",
                "level": "PROVIDER",
                "mode": "ONE_TO_ONE",
                "gold_columns": [],
                "trust_fields": [],
                "coverage": "PENDING_MENTOR",
                "extra": 1,
            }
        )


# --- Part 3: finding key (docs/specs/01-contracts.md) ---

K = FindingKey
ADDR_KEY = "addr:145 s st|boston ma 02111"


def test_k01_provider_key() -> None:
    key = K.for_provider("degree", "HPHC")
    assert key.location_key == PROVIDER_SCOPE == "provider"
    assert key.row_id() == "degree:provider"


def test_k02_location_key_row_id() -> None:
    assert K.for_location("phone", "HPHC", "3038479374").row_id() == "phone:3038479374"


def test_k03_addr_key_is_reported_only() -> None:
    assert K.for_location("practice_locations", "HPHC", ADDR_KEY).is_reported_only() is True


def test_k04_location_field_at_provider_scope_refused() -> None:
    with pytest.raises(ValidationError, match="phone is a location field"):
        K.for_provider("phone", "HPHC")


def test_k05_provider_field_at_location_refused() -> None:
    with pytest.raises(ValidationError, match="degree is a provider field"):
        K.for_location("degree", "HPHC", "3038479374")


def test_k06_location_field_with_provider_key_refused() -> None:
    with pytest.raises(ValidationError):
        K.for_location("phone", "HPHC", "provider")


def test_k07_empty_address_refused() -> None:
    with pytest.raises(ValidationError, match="empty address"):
        K.for_location("phone", "HPHC", "addr:")


def test_k08_unknown_field_refused() -> None:
    with pytest.raises(ValidationError, match="unknown field"):
        K.for_location("fax", "HPHC", "3038479374")


def test_k09_empty_representation_refused() -> None:
    with pytest.raises(ValidationError):
        K.for_provider("degree", "")


def test_k10_different_locations_not_equal() -> None:
    assert K.for_location("phone", "HPHC", "loc1") != K.for_location("phone", "HPHC", "loc2")


def test_k11_different_representations_not_equal() -> None:
    assert K.for_location("phone", "HPHC", "loc1") != K.for_location("phone", "REP_B", "loc1")


def test_k12_equal_keys_collapse_in_a_set() -> None:
    keys = {K.for_location("phone", "HPHC", "loc1"), K.for_location("phone", "HPHC", "loc1")}
    assert len(keys) == 1


def test_k13_key_is_frozen() -> None:
    key = K.for_location("phone", "HPHC", "loc1")
    with pytest.raises(ValidationError):
        key.location_key = "loc2"


def test_k14_round_trip_addr_key() -> None:
    key = K.for_location("practice_locations", "HPHC", ADDR_KEY)
    assert K.from_str(key.to_str()) == key


def test_k15_from_str_refuses_junk() -> None:
    with pytest.raises(ValueError):
        K.from_str("not a key")


def test_k16_representation_kept_exactly() -> None:
    key = K.for_provider("degree", " HPHC")
    assert key.representation == " HPHC"
    assert key != K.for_provider("degree", "HPHC")


# Extra tests for Part 3 rules that no numbered case covers


def test_key_rule2_provider_field_with_addr_key_refused() -> None:
    with pytest.raises(ValidationError, match="degree is a provider field"):
        K.for_location("degree", "HPHC", ADDR_KEY)


def test_key_rule4_empty_location_key_refused() -> None:
    with pytest.raises(ValidationError):
        K.for_location("phone", "HPHC", "")


def test_key_rule4_non_string_part_not_coerced() -> None:
    with pytest.raises(ValidationError):
        K.model_validate(
            {"field_name": "phone", "representation": "HPHC", "location_key": 3038479374}
        )


def test_key_rule4_location_key_case_kept() -> None:
    assert K.for_location("phone", "HPHC", "ADDR:X").location_key == "ADDR:X"


def test_key_rule6_equal_keys_hash_equal_and_work_as_dict_keys() -> None:
    a = K.for_location("phone", "HPHC", "loc1")
    b = K.for_location("phone", "HPHC", "loc1")
    assert a == b
    assert hash(a) == hash(b)
    assert {a: "decision"}[b] == "decision"


def test_key_rule8_round_trip_awkward_characters() -> None:
    key = K.for_location("phone", "A:B|C", 'addr:1 "x" st: unit|2, \\ é')
    text = key.to_str()
    assert json.loads(text) == [key.field_name, key.representation, key.location_key]
    assert K.from_str(text) == key


@pytest.mark.parametrize(
    "text",
    [
        "",
        '["phone","HPHC"]',
        '["phone","HPHC","loc1","extra"]',
        '["phone","HPHC",1]',
        '{"field_name":"phone","representation":"HPHC","location_key":"loc1"}',
        '"phone:loc1"',
        '["fax","HPHC","loc1"]',
        '["phone","HPHC","provider"]',
    ],
)
def test_key_rule9_from_str_never_guesses(text: str) -> None:
    with pytest.raises(ValueError):
        K.from_str(text)


def test_key_is_provider_scope() -> None:
    assert K.for_provider("degree", "HPHC").is_provider_scope() is True
    assert K.for_location("phone", "HPHC", "loc1").is_provider_scope() is False


def test_key_gold_location_is_not_reported_only() -> None:
    assert K.for_location("phone", "HPHC", "3038479374").is_reported_only() is False


def test_key_positional_form_from_spec() -> None:
    assert K("degree", "HPHC", "provider") == K.for_provider("degree", "HPHC")
    assert K("phone", "HPHC", "3038479374") == K.for_location("phone", "HPHC", "3038479374")


def test_key_rule10_display_text_refused() -> None:
    with pytest.raises(ValidationError):
        K.model_validate(
            {
                "field_name": "phone",
                "representation": "HPHC",
                "location_key": "loc1",
                "address": "145 S St, Boston MA",
            }
        )


# --- Part 4: evidence (docs/specs/01-contracts-02.md) ---

NPPES_URL = "https://npiregistry.cms.hhs.gov/api/?number=1013489194&version=2.1"
RETRIEVED = datetime(2026, 11, 9, 22, 35, 7, tzinfo=UTC)
IST = timezone(timedelta(hours=5, minutes=30))
OFFICE = LocationRef(display_address="145 S St, Boston MA 02111", location_name="Main office")


def _assertion(**overrides: Any) -> EvidenceAssertion:
    """The spec's NPPES degree example, with any field replaced."""
    data: dict[str, Any] = {
        "case_id": "CASE-637551BD11B2",
        "npi": "1013489194",
        "field_name": "degree",
        "data_group": DataGroup.IDENTITY,
        "source_id": SourceId.NPPES,
        "raw_value": "LMHC",
        "normalized_value": None,
        "status": AssertionStatus.FOUND,
        "status_detail": None,
        "url_or_identifier": NPPES_URL,
        "retrieved_at": RETRIEVED,
        "source_last_update": date(2024, 3, 4),
        "quality_label": QualityLabel.STATED,
        "adapter_version": "nppes-0.1",
        "location_ref": None,
    }
    data.update(overrides)
    return EvidenceAssertion.model_validate(data)


def _not_found(**overrides: Any) -> EvidenceAssertion:
    """A NOT_FOUND version of the example."""
    data: dict[str, Any] = {"status": AssertionStatus.NOT_FOUND, "raw_value": None}
    data.update(overrides)
    return _assertion(**data)


def _bundle(*assertions: EvidenceAssertion, **overrides: Any) -> EvidenceBundle:
    """A bundle matching the example's case, NPI, source and data group."""
    data: dict[str, Any] = {
        "case_id": "CASE-637551BD11B2",
        "npi": "1013489194",
        "source_id": SourceId.NPPES,
        "data_group": DataGroup.IDENTITY,
        "gold_version": "gold-2026-11-01",
        "trust_matrix_version": "trust-v1",
        "correlation_id": "corr-1",
        "created_at": RETRIEVED,
        "assertions": assertions or (_assertion(),),
    }
    data.update(overrides)
    return EvidenceBundle.model_validate(data)


def test_e01_nppes_degree_example_valid() -> None:
    a = _assertion()
    assert a.raw_value == "LMHC"
    assert a.retrieved_at == RETRIEVED


def test_e02_found_needs_raw_value() -> None:
    with pytest.raises(ValidationError):
        _assertion(raw_value="")


def test_e03_not_found_allows_no_value() -> None:
    with pytest.raises(ValidationError, match="no value allowed"):
        _assertion(status=AssertionStatus.NOT_FOUND, raw_value="LMHC")


def test_e04_not_found_with_status_detail_valid() -> None:
    assert _not_found(status_detail="NOT_IN_EXTRACT").status_detail == "NOT_IN_EXTRACT"


def test_e05_short_npi_refused() -> None:
    with pytest.raises(ValidationError):
        _assertion(npi="12345")


def test_e06_leading_zero_npi_kept() -> None:
    assert _assertion(npi="0123456789").npi == "0123456789"


def test_e07_unknown_field_refused() -> None:
    with pytest.raises(ValidationError, match="unknown field"):
        _assertion(field_name="fax")


def test_e08_raw_value_over_2000_refused() -> None:
    with pytest.raises(ValidationError):
        _assertion(raw_value="x" * 2001)


def test_e09_naive_retrieved_at_refused() -> None:
    with pytest.raises(ValidationError):
        _assertion(retrieved_at=datetime(2026, 11, 9, 22, 35, 7))


def test_e10_found_location_field_needs_office() -> None:
    with pytest.raises(ValidationError, match="location field needs an office"):
        _assertion(field_name="phone", data_group=DataGroup.LOCATION, raw_value="3038479374")


def test_e11_provider_field_has_no_office() -> None:
    with pytest.raises(ValidationError, match="provider field has no office"):
        _assertion(location_ref=OFFICE)


def test_e12_empty_url_or_identifier_refused() -> None:
    with pytest.raises(ValidationError):
        _assertion(url_or_identifier="")


def test_e13_google_search_trust_name() -> None:
    assert SourceId.GOOGLE_SEARCH.trust_matrix_name == "Google Searches"


def test_e14_every_source_is_in_trust_matrix() -> None:
    real = set(_lines(FIXTURES / "trust_source_systems.txt"))
    assert {s.trust_matrix_name for s in SourceId} <= real


def test_e15_mixed_sources_refused() -> None:
    caqh = _assertion(source_id=SourceId.CAQH, url_or_identifier="caqh:row-1")
    with pytest.raises(ValidationError, match="mixed sources"):
        _bundle(caqh, _assertion())


def test_e16_empty_bundle_refused() -> None:
    with pytest.raises(ValidationError):
        _bundle(assertions=())


def test_e17_bundle_keeps_order() -> None:
    items = (
        _assertion(field_name="degree"),
        _assertion(field_name="gender", raw_value="F"),
        _assertion(field_name="npi_type", raw_value="1"),
    )
    assert _bundle(*items).assertions == items


def test_e18_assertion_is_frozen() -> None:
    a = _assertion()
    with pytest.raises(ValidationError):
        a.raw_value = "MD"


def test_e19_bundle_json_round_trip() -> None:
    b = _bundle(_assertion(), _not_found(field_name="gender", status_detail="NO_MATCH"))
    assert EvidenceBundle.model_validate_json(b.model_dump_json()) == b


def test_e20_empty_gold_version_refused() -> None:
    with pytest.raises(ValidationError):
        _bundle(gold_version="")


# Extra tests for Part 4 rules that no numbered case covers


def test_ev_rule3_not_found_normalized_value_refused() -> None:
    with pytest.raises(ValidationError, match="no value allowed"):
        _not_found(normalized_value="lmhc")


def test_ev_rule3_found_without_normalized_value_valid() -> None:
    assert _assertion(normalized_value=None).normalized_value is None


@pytest.mark.parametrize(
    "status",
    [AssertionStatus.NO_VALUE, AssertionStatus.UNAVAILABLE, AssertionStatus.AMBIGUOUS],
)
def test_ev_rule3_other_statuses_refuse_values(status: AssertionStatus) -> None:
    with pytest.raises(ValidationError, match="no value allowed"):
        _assertion(status=status)


def test_ev_rule4_raw_value_kept_exactly() -> None:
    assert _assertion(raw_value="  lmhc ").raw_value == "  lmhc "


def test_ev_rule5_raw_value_of_2000_valid() -> None:
    assert _assertion(raw_value="x" * 2000).raw_value == "x" * 2000


def test_ev_rule7_retrieved_at_stored_in_utc() -> None:
    a = _assertion(retrieved_at=datetime(2026, 11, 10, 4, 5, 7, tzinfo=IST))
    assert a.retrieved_at == RETRIEVED
    assert a.retrieved_at.utcoffset() == timedelta(0)


def test_ev_rule7_source_last_update_optional() -> None:
    assert _assertion(source_last_update=None).source_last_update is None


def test_ev_rule7_bundle_created_at_stored_in_utc() -> None:
    b = _bundle(created_at=datetime(2026, 11, 10, 4, 5, 7, tzinfo=IST))
    assert b.created_at.utcoffset() == timedelta(0)


def test_ev_rule8_not_found_location_field_without_office_valid() -> None:
    assert _not_found(field_name="phone", data_group=DataGroup.LOCATION).location_ref is None


def test_ev_rule8_found_location_field_with_office_valid() -> None:
    a = _assertion(
        field_name="phone",
        data_group=DataGroup.LOCATION,
        raw_value="3038479374",
        location_ref=OFFICE,
    )
    assert a.location_ref == OFFICE


def test_ev_rule8_not_found_provider_field_with_office_refused() -> None:
    with pytest.raises(ValidationError, match="provider field has no office"):
        _not_found(location_ref=OFFICE)


def test_ev_rule10_conclusions_refused() -> None:
    with pytest.raises(ValidationError):
        _assertion(matches_directory=True)


@pytest.mark.parametrize(
    "override",
    [
        {"case_id": "CASE-OTHER"},
        {"npi": "0123456789"},
        {"data_group": DataGroup.ATTESTATION},
    ],
)
def test_ev_rule12_bundle_parts_must_match(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _bundle(_assertion(), _assertion(**override))


def test_ev_rule13_unavailable_only_bundle_valid() -> None:
    failed = _assertion(
        status=AssertionStatus.UNAVAILABLE, raw_value=None, status_detail="HTTP 503"
    )
    assert _bundle(failed).assertions[0].status is AssertionStatus.UNAVAILABLE


def test_ev_rule16_assertion_with_office_json_round_trip() -> None:
    a = _assertion(
        field_name="phone",
        data_group=DataGroup.LOCATION,
        raw_value="(303) 847-9374",
        location_ref=LocationRef(display_address="145 S St", practice_location_id="PL-1"),
    )
    assert EvidenceAssertion.model_validate_json(a.model_dump_json()) == a


def test_ev_location_ref_needs_display_address() -> None:
    with pytest.raises(ValidationError):
        LocationRef(display_address="")


# --- Part 5: search plan (docs/specs/01-contracts-02.md) ---
# Trust weights below are example data for the shape only, not trust-matrix values.


def _task(**overrides: Any) -> SourceTask:
    """The spec example's nppes:identity task, with any field replaced."""
    data: dict[str, Any] = {
        "task_id": "nppes:identity",
        "source_id": SourceId.NPPES,
        "data_group": DataGroup.IDENTITY,
        "fields": ("npi_type", "provider_name", "gender"),
        "trust_weights": {"npi_type": 0.85, "provider_name": 0.30, "gender": 0.30},
        "search_params": {"npi": "1013489194"},
        "origin": TaskOrigin.TRUST_MATRIX,
    }
    data.update(overrides)
    return SourceTask.model_validate(data)


def _plan(**overrides: Any) -> SearchPlan:
    """The spec's example plan, with any field replaced."""
    data: dict[str, Any] = {
        "case_id": "CASE-637551BD11B2",
        "npi": "1013489194",
        "case_type": CaseType.TARGETED,
        "gold_version": "gold-2026-11-01",
        "trust_matrix_version": "client-v2.0-caqh-nppes-web-google-2026-10-21",
        "plan_version": "planner-0.1",
        "requested_fields": ("npi_type", "provider_name", "gender", "office_hours"),
        "tasks": (_task(),),
        "skipped_sources": (),
        "unplanned_fields": (
            UnplannedField(field_name="office_hours", reason=UnplannedReason.NO_TRUST_ROWS),
        ),
    }
    data.update(overrides)
    return SearchPlan.model_validate(data)


def _three_task_plan() -> SearchPlan:
    tasks = (
        _task(),
        _task(
            task_id="caqh:attestation",
            source_id=SourceId.CAQH,
            data_group=DataGroup.ATTESTATION,
            fields=("degree", "specialty"),
            trust_weights={"degree": 0.9, "specialty": 0.8},
            search_params={"npi": "1013489194"},
        ),
        _task(
            task_id="provider_website:location",
            source_id=SourceId.PROVIDER_WEBSITE,
            data_group=DataGroup.LOCATION,
            fields=("phone", "website"),
            trust_weights={"phone": 0.6, "website": 0.7},
            search_params={"url": "https://example.org"},
        ),
    )
    return _plan(
        requested_fields=(
            "npi_type",
            "provider_name",
            "gender",
            "degree",
            "specialty",
            "phone",
            "website",
        ),
        tasks=tasks,
        unplanned_fields=(),
    )


def test_s01_example_plan_valid() -> None:
    plan = _plan()
    assert plan.tasks[0].task_id == "nppes:identity"


def test_s02_requested_field_not_accounted_for() -> None:
    task = _task(
        fields=("npi_type", "provider_name"), trust_weights={"npi_type": 0.85, "provider_name": 0.3}
    )
    with pytest.raises(ValidationError, match="not accounted for"):
        _plan(tasks=(task,))


def test_s03_field_in_task_and_unplanned_refused() -> None:
    with pytest.raises(ValidationError):
        _plan(
            requested_fields=("npi_type", "provider_name", "gender"),
            unplanned_fields=(
                UnplannedField(field_name="gender", reason=UnplannedReason.NO_ALLOWED_SOURCE),
            ),
        )


def test_s04_pending_mentor_field_in_task_refused() -> None:
    task = _task(
        fields=("npi_type", "provider_name", "gender", "office_hours"),
        trust_weights={"npi_type": 0.85, "provider_name": 0.3, "gender": 0.3, "office_hours": 0.5},
    )
    with pytest.raises(ValidationError, match="no trust rows"):
        _plan(tasks=(task,), unplanned_fields=())


def test_s05_task_field_not_requested_refused() -> None:
    with pytest.raises(ValidationError):
        _plan(
            requested_fields=("npi_type", "provider_name", "office_hours"),
        )


def test_s06_duplicate_task_refused() -> None:
    first = _task(fields=("npi_type",), trust_weights={"npi_type": 0.85})
    second = _task(
        fields=("provider_name", "gender"), trust_weights={"provider_name": 0.3, "gender": 0.3}
    )
    with pytest.raises(ValidationError, match="duplicate task"):
        _plan(tasks=(first, second))


def test_s07_task_id_format() -> None:
    with pytest.raises(ValidationError, match="must be 'nppes:identity'"):
        _task(task_id="nppes-identity")


def test_s08_missing_trust_weight_refused() -> None:
    with pytest.raises(ValidationError):
        _task(trust_weights={"npi_type": 0.85, "provider_name": 0.30})


@pytest.mark.parametrize("weight", [0, 1.2, -0.1])
def test_s09_weight_out_of_range_refused(weight: float) -> None:
    with pytest.raises(ValidationError):
        _task(trust_weights={"npi_type": weight, "provider_name": 0.3, "gender": 0.3})


def test_s10_secret_search_param_refused() -> None:
    with pytest.raises(ValidationError, match="secrets not allowed"):
        _task(search_params={"api_key": "x"})


def test_s11_empty_search_params_refused() -> None:
    with pytest.raises(ValidationError):
        _task(search_params={})


def test_s12_skipped_and_task_refused() -> None:
    skip = SkippedSource(
        source_id=SourceId.NPPES, data_group=DataGroup.IDENTITY, reason=SkipReason.NOT_ALLOWED
    )
    with pytest.raises(ValidationError):
        _plan(skipped_sources=(skip,))


def test_s13_empty_requested_fields_refused() -> None:
    with pytest.raises(ValidationError):
        _plan(requested_fields=(), tasks=(), unplanned_fields=())


def test_s14_tasks_for_field() -> None:
    plan = _plan()
    assert plan.tasks_for_field("gender") == (plan.tasks[0],)


def test_s15_task_order_kept() -> None:
    plan = _three_task_plan()
    assert [t.task_id for t in plan.tasks] == [
        "nppes:identity",
        "caqh:attestation",
        "provider_website:location",
    ]


def test_s16_plan_json_round_trip() -> None:
    plan = _plan()
    assert SearchPlan.model_validate_json(plan.model_dump_json()) == plan


def test_s17_plan_is_frozen() -> None:
    plan = _plan()
    with pytest.raises(ValidationError):
        plan.tasks[0].fields = ("gender",)


def test_s18_no_tasks_all_unplanned_valid() -> None:
    plan = _plan(
        requested_fields=("office_hours", "gender"),
        tasks=(),
        unplanned_fields=(
            UnplannedField(field_name="office_hours", reason=UnplannedReason.NO_TRUST_ROWS),
            UnplannedField(field_name="gender", reason=UnplannedReason.NO_ALLOWED_SOURCE),
        ),
    )
    assert plan.tasks == ()


# Extra tests for Part 5 rules that no numbered case covers


@pytest.mark.parametrize("override", [{"npi": "12345"}, {"plan_version": ""}, {"case_id": ""}])
def test_sp_rule1_plan_header(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _plan(**override)


def test_sp_rule2_unknown_requested_field_refused() -> None:
    with pytest.raises(ValidationError, match="unknown field"):
        _plan(requested_fields=("npi_type", "provider_name", "gender", "office_hours", "fax"))


def test_sp_rule2_duplicate_requested_field_refused() -> None:
    with pytest.raises(ValidationError):
        _plan(requested_fields=("npi_type", "provider_name", "gender", "office_hours", "gender"))


def test_sp_rule3_unplanned_field_not_requested_refused() -> None:
    with pytest.raises(ValidationError):
        _plan(
            unplanned_fields=(
                UnplannedField(field_name="office_hours", reason=UnplannedReason.NO_TRUST_ROWS),
                UnplannedField(field_name="weekend_hours", reason=UnplannedReason.NO_TRUST_ROWS),
            )
        )


def test_sp_rule3_unplanned_field_twice_refused() -> None:
    entry = UnplannedField(field_name="office_hours", reason=UnplannedReason.NO_TRUST_ROWS)
    with pytest.raises(ValidationError):
        _plan(unplanned_fields=(entry, entry))


def test_sp_rule5_empty_task_fields_refused() -> None:
    with pytest.raises(ValidationError):
        _task(fields=(), trust_weights={})


def test_sp_rule5_repeated_task_field_refused() -> None:
    with pytest.raises(ValidationError):
        _task(fields=("npi_type", "npi_type"), trust_weights={"npi_type": 0.85})


def test_sp_rule7_extra_weight_refused() -> None:
    with pytest.raises(ValidationError):
        _task(trust_weights={"npi_type": 0.85, "provider_name": 0.3, "gender": 0.3, "degree": 0.5})


def test_sp_rule7_weight_of_one_valid() -> None:
    task = _task(trust_weights={"npi_type": 1, "provider_name": 0.3, "gender": 0.3})
    assert task.trust_weights["npi_type"] == 1


@pytest.mark.parametrize("params", [{"": "x"}, {"npi": ""}])
def test_sp_rule8_empty_param_key_or_value_refused(params: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _task(search_params=params)


@pytest.mark.parametrize(
    "key", ["api_key", "API_KEY", "TOKEN", "auth_token", "client_secret", "db_password"]
)
def test_sp_rule9_secret_keys_refused_and_value_hidden(key: str) -> None:
    with pytest.raises(ValidationError, match="secrets not allowed") as caught:
        _task(search_params={"npi": "1013489194", key: "s3cr3t-VALUE"})
    assert "s3cr3t-VALUE" not in str(caught.value)


def test_sp_rule9_secret_value_hidden_in_plan_errors() -> None:
    with pytest.raises(ValidationError) as caught:
        SearchPlan.model_validate(
            {
                "case_id": "C",
                "npi": "1013489194",
                "case_type": "TARGETED",
                "gold_version": "g",
                "trust_matrix_version": "t",
                "plan_version": "p",
                "requested_fields": ["gender"],
                "tasks": [
                    {
                        "task_id": "nppes:identity",
                        "source_id": "nppes",
                        "data_group": "IDENTITY",
                        "fields": ["gender"],
                        "trust_weights": {"gender": 0.3},
                        "search_params": {"password": "s3cr3t-VALUE"},
                        "origin": "TRUST_MATRIX",
                    }
                ],
                "skipped_sources": [],
                "unplanned_fields": [],
            }
        )
    assert "s3cr3t-VALUE" not in str(caught.value)


def test_sp_mappings_are_read_only() -> None:
    task = _task()
    with pytest.raises(TypeError):
        task.trust_weights["gender"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        task.search_params["npi"] = "x"  # type: ignore[index]


def test_sp_task_lookup() -> None:
    plan = _plan()
    assert plan.task(SourceId.NPPES, DataGroup.IDENTITY) is plan.tasks[0]
    with pytest.raises(KeyError):
        plan.task(SourceId.CAQH, DataGroup.IDENTITY)


def test_sp_tasks_for_unplanned_field_is_empty() -> None:
    assert _plan().tasks_for_field("office_hours") == ()


def test_sp_discovery_task_and_skip_detail_valid() -> None:
    discovery = _task(
        task_id="google_search:location",
        source_id=SourceId.GOOGLE_SEARCH,
        data_group=DataGroup.LOCATION,
        fields=("website",),
        trust_weights={"website": 0.5},
        search_params={"query": "Jane Doe LMHC Boston"},
        origin=TaskOrigin.DISCOVERY,
    )
    skip = SkippedSource(
        source_id=SourceId.CAQH,
        data_group=DataGroup.IDENTITY,
        reason=SkipReason.OUT_OF_COVERAGE,
        detail="not in CAQH extract",
    )
    plan = _plan(
        case_type=CaseType.COVERAGE,
        requested_fields=("npi_type", "provider_name", "gender", "office_hours", "website"),
        tasks=(_task(), discovery),
        skipped_sources=(skip,),
    )
    assert plan.tasks_for_field("website") == (discovery,)


def test_sp_extra_keys_refused() -> None:
    with pytest.raises(ValidationError):
        _task(score=0.9)
    with pytest.raises(ValidationError):
        _plan(route="HITL")
