"""Tests that every contract validates good examples and rejects bad ones, including a sample report."""

import json

import pytest

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
