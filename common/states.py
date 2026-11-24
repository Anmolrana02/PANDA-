"""State names for the agent case, the dispatcher and the portal, and which transitions are allowed.

Each machine has one move table below; no other file defines its own list.
Statuses are StrEnums, so they save to JSON, Cosmos and Postgres as plain text.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast

__all__ = [
    "AGENT_CASE_MOVES",
    "DISPATCH_MOVES",
    "PORTAL_BATCH_MOVES",
    "AgentCaseState",
    "DispatchState",
    "InvalidTransition",
    "PortalBatchState",
    "allowed_moves",
    "can_transition",
    "is_final",
    "require_transition",
]


class AgentCaseState(StrEnum):
    """Status of one NPI investigation."""

    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RETRIEVING = "RETRIEVING"
    VALIDATING = "VALIDATING"
    SCORING = "SCORING"
    ROUTING = "ROUTING"
    CLOSED = "CLOSED"
    HITL_PENDING = "HITL_PENDING"
    CANCELLED = "CANCELLED"


class DispatchState(StrEnum):
    """Status of the job that hands a case to the graph."""

    PENDING = "PENDING"
    DISPATCHING = "DISPATCHING"
    DONE = "DONE"
    EXHAUSTED = "EXHAUSTED"


class PortalBatchState(StrEnum):
    """Status of a reviewer batch in the portal."""

    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEWER_DECIDED = "REVIEWER_DECIDED"
    EXPERT_REVIEW = "EXPERT_REVIEW"
    CLOSED = "CLOSED"


_A = AgentCaseState
_D = DispatchState
_P = PortalBatchState

AGENT_CASE_MOVES: Mapping[AgentCaseState, frozenset[AgentCaseState]] = MappingProxyType(
    {
        _A.CREATED: frozenset({_A.PLANNED, _A.CANCELLED}),
        _A.PLANNED: frozenset({_A.RETRIEVING, _A.CANCELLED}),
        _A.RETRIEVING: frozenset({_A.VALIDATING, _A.CANCELLED}),
        _A.VALIDATING: frozenset({_A.SCORING, _A.CANCELLED}),
        _A.SCORING: frozenset({_A.ROUTING, _A.CANCELLED}),
        _A.ROUTING: frozenset({_A.CLOSED, _A.HITL_PENDING, _A.CANCELLED}),
        _A.CLOSED: frozenset(),
        _A.HITL_PENDING: frozenset(),
        _A.CANCELLED: frozenset(),
    }
)

DISPATCH_MOVES: Mapping[DispatchState, frozenset[DispatchState]] = MappingProxyType(
    {
        _D.PENDING: frozenset({_D.DISPATCHING}),
        _D.DISPATCHING: frozenset({_D.DONE, _D.PENDING, _D.EXHAUSTED}),
        _D.DONE: frozenset(),
        _D.EXHAUSTED: frozenset(),
    }
)

PORTAL_BATCH_MOVES: Mapping[PortalBatchState, frozenset[PortalBatchState]] = MappingProxyType(
    {
        _P.OPEN: frozenset({_P.ASSIGNED}),
        _P.ASSIGNED: frozenset({_P.IN_PROGRESS}),
        _P.IN_PROGRESS: frozenset({_P.REVIEWER_DECIDED}),
        _P.REVIEWER_DECIDED: frozenset({_P.CLOSED, _P.EXPERT_REVIEW}),
        _P.EXPERT_REVIEW: frozenset({_P.CLOSED}),
        _P.CLOSED: frozenset(),
    }
)

# Machine label and move table, keyed by the exact enum class.
_MACHINES: Mapping[type, tuple[str, Mapping[Any, frozenset[Any]]]] = MappingProxyType(
    {
        AgentCaseState: ("agent case", AGENT_CASE_MOVES),
        DispatchState: ("dispatch job", DISPATCH_MOVES),
        PortalBatchState: ("portal batch", PORTAL_BATCH_MOVES),
    }
)


class InvalidTransition(ValueError):
    """A move that the state machine does not allow."""

    def __init__(self, label: str, current: StrEnum, proposed: StrEnum) -> None:
        super().__init__(f"Cannot move {label} from {current} to {proposed}")
        self.current = current
        self.proposed = proposed


def _machine(state: object) -> tuple[str, Mapping[Any, frozenset[Any]]]:
    """Return the label and move table for a status, or raise TypeError."""
    machine = _MACHINES.get(type(state))
    if machine is None:
        raise TypeError(f"Not a known status type: {type(state).__name__}")
    return machine


def _same_machine(current: object, proposed: object) -> tuple[str, Mapping[Any, frozenset[Any]]]:
    """Refuse to compare statuses from different machines (StrEnums compare equal by text)."""
    if type(current) is not type(proposed):
        raise TypeError(f"Cannot compare {type(current).__name__} with {type(proposed).__name__}")
    return _machine(current)


def allowed_moves[S: (AgentCaseState, DispatchState, PortalBatchState)](state: S) -> frozenset[S]:
    """Statuses that `state` may move to next."""
    _, moves = _machine(state)
    return cast(frozenset[S], moves[state])


def is_final[S: (AgentCaseState, DispatchState, PortalBatchState)](state: S) -> bool:
    """True if nothing may move out of `state`."""
    return not allowed_moves(state)


def can_transition[S: (AgentCaseState, DispatchState, PortalBatchState)](
    current: S, proposed: S
) -> bool:
    """True if moving from `current` to `proposed` is allowed."""
    _, moves = _same_machine(current, proposed)
    return proposed in moves[current]


def require_transition[S: (AgentCaseState, DispatchState, PortalBatchState)](
    current: S, proposed: S
) -> None:
    """Raise InvalidTransition unless moving from `current` to `proposed` is allowed."""
    label, moves = _same_machine(current, proposed)
    if proposed not in moves[current]:
        raise InvalidTransition(label, current, proposed)
