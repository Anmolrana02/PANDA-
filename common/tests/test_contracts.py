"""Tests that every contract validates good examples and rejects bad ones, including a sample report."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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
