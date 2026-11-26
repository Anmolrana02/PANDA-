"""Search Plan: which sources to ask for which fields, built by the planner from the trust matrix.

The planner node writes it and the evidence node follows it in order. One
SourceTask produces one EvidenceBundle (same source, same data group). This
file only defines and checks the shape; it never chooses or reorders sources.
Rules: docs/specs/01-contracts-02.md Part 5.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from common.evidence import DataGroup, NonEmptyStr, Npi, SourceId
from common.field_catalog import Coverage, UnknownField, get_field

__all__ = [
    "SECRET_WORDS",
    "CaseType",
    "SearchPlan",
    "SkipReason",
    "SkippedSource",
    "SourceTask",
    "TaskOrigin",
    "UnplannedField",
    "UnplannedReason",
    "task_id_for",
]

SECRET_WORDS: tuple[str, ...] = ("key", "token", "secret", "password")
"""A search_params key containing one of these (any case) is refused."""

Weight = Annotated[float, Field(gt=0, le=1)]


class CaseType(StrEnum):
    """Why the case was opened."""

    TARGETED = "TARGETED"
    COVERAGE = "COVERAGE"


class TaskOrigin(StrEnum):
    """Why a task is in the plan."""

    TRUST_MATRIX = "TRUST_MATRIX"
    DISCOVERY = "DISCOVERY"


class SkipReason(StrEnum):
    """Why a (source, data group) was left out."""

    INACTIVE_ROW = "INACTIVE_ROW"
    NOT_ALLOWED = "NOT_ALLOWED"
    NO_SEARCH_INPUT = "NO_SEARCH_INPUT"
    DUPLICATE = "DUPLICATE"
    OUT_OF_COVERAGE = "OUT_OF_COVERAGE"


class UnplannedReason(StrEnum):
    """Why a requested field has no task."""

    NO_TRUST_ROWS = "NO_TRUST_ROWS"
    NO_ALLOWED_SOURCE = "NO_ALLOWED_SOURCE"


class _Frozen(BaseModel):
    # hide_input_in_errors keeps a refused secret value out of error text, logs and traces.
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


def task_id_for(source_id: SourceId, data_group: DataGroup) -> str:
    """The only allowed task_id for a (source, data group), e.g. 'nppes:identity'."""
    return f"{source_id.value}:{data_group.value.lower()}"


def _repeated(items: Iterable[str]) -> list[str]:
    return [item for item, count in Counter(items).items() if count > 1]


class SourceTask(_Frozen):
    """Ask one source for one data group's fields."""

    task_id: str
    source_id: SourceId
    data_group: DataGroup
    fields: Annotated[tuple[str, ...], Field(min_length=1)]
    trust_weights: Mapping[str, Weight]
    search_params: Annotated[Mapping[NonEmptyStr, NonEmptyStr], Field(min_length=1)]
    origin: TaskOrigin

    @field_validator("trust_weights", "search_params")
    @classmethod
    def _read_only(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return MappingProxyType(dict(value))

    @field_serializer("trust_weights", "search_params")
    def _as_dict(self, value: Mapping[str, object]) -> dict[str, object]:
        return dict(value)

    @field_validator("search_params")
    @classmethod
    def _no_secrets(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        for key in value:
            if any(word in key.lower() for word in SECRET_WORDS):
                raise ValueError(f"secrets not allowed in search_params (key {key!r})")
        return value

    @model_validator(mode="after")
    def _check_task(self) -> Self:
        expected = task_id_for(self.source_id, self.data_group)
        if self.task_id != expected:
            raise ValueError(f"task_id {self.task_id!r} must be {expected!r}")
        if repeated := _repeated(self.fields):
            raise ValueError(f"{self.task_id}: field listed more than once: {repeated}")
        if set(self.trust_weights) != set(self.fields):
            raise ValueError(f"{self.task_id}: trust_weights needs exactly one entry per field")
        return self


class SkippedSource(_Frozen):
    """A (source, data group) the planner left out, and why."""

    source_id: SourceId
    data_group: DataGroup
    reason: SkipReason
    detail: str | None = None


class UnplannedField(_Frozen):
    """A requested field no source will be asked about, and why."""

    field_name: str
    reason: UnplannedReason


class SearchPlan(_Frozen):
    """The to-do list for one case. Task order is kept exactly, so a replay matches."""

    case_id: NonEmptyStr
    npi: Npi
    case_type: CaseType
    gold_version: NonEmptyStr
    trust_matrix_version: NonEmptyStr
    plan_version: NonEmptyStr
    requested_fields: Annotated[tuple[str, ...], Field(min_length=1)]
    tasks: tuple[SourceTask, ...]
    skipped_sources: tuple[SkippedSource, ...] = ()
    unplanned_fields: tuple[UnplannedField, ...] = ()

    @model_validator(mode="after")
    def _check_plan(self) -> Self:
        self._check_requested()
        self._check_tasks()
        self._check_every_field_accounted_for()
        return self

    def _check_requested(self) -> None:
        for name in self.requested_fields:
            try:
                get_field(name)
            except UnknownField:
                raise ValueError(f"unknown field: {name!r}") from None
        if repeated := _repeated(self.requested_fields):
            raise ValueError(f"requested field listed more than once: {repeated}")

    def _check_tasks(self) -> None:
        requested = set(self.requested_fields)
        seen: set[tuple[SourceId, DataGroup]] = set()
        for task in self.tasks:
            for name in task.fields:
                if name not in requested:
                    raise ValueError(f"{task.task_id}: field {name!r} is not in requested_fields")
                if get_field(name).coverage is not Coverage.COVERED:
                    raise ValueError(f"{task.task_id}: field {name!r} has no trust rows")
            pair = (task.source_id, task.data_group)
            if pair in seen:
                raise ValueError(f"duplicate task: {task.task_id}")
            seen.add(pair)
        for skip in self.skipped_sources:
            if (skip.source_id, skip.data_group) in seen:
                raise ValueError(
                    f"{task_id_for(skip.source_id, skip.data_group)} is both skipped and a task"
                )

    def _check_every_field_accounted_for(self) -> None:
        unplanned = [entry.field_name for entry in self.unplanned_fields]
        if repeated := _repeated(unplanned):
            raise ValueError(f"unplanned field listed more than once: {repeated}")
        tasked = {name for task in self.tasks for name in task.fields}
        for name in unplanned:
            if name not in self.requested_fields:
                raise ValueError(f"unplanned field {name!r} is not in requested_fields")
            if name in tasked:
                raise ValueError(f"field {name!r} is both in a task and unplanned")
        missing = [n for n in self.requested_fields if n not in tasked and n not in unplanned]
        if missing:
            raise ValueError(f"requested fields not accounted for: {missing}")

    def tasks_for_field(self, name: str) -> tuple[SourceTask, ...]:
        """Tasks that ask about `name`, in plan order (empty if none)."""
        return tuple(task for task in self.tasks if name in task.fields)

    def task(self, source_id: SourceId, data_group: DataGroup) -> SourceTask:
        """The task for (source, data group). Raises KeyError if there is none."""
        for task in self.tasks:
            if task.source_id is source_id and task.data_group is data_group:
                return task
        raise KeyError(task_id_for(source_id, data_group))
