# Day 2 session plan: 01 - contracts, Part 5 `common/search_plan.py` (2026-11-25)

## Context

The planner node (Phase 3) decides which sources to ask for which fields, and
the evidence node carries that out. They need one fixed, replayable shape for
that to-do list. Spec: `docs/specs/01-contracts-02.md`, Part 5. Today
`common/search_plan.py` holds only a docstring.

The repo is in this state:
- You added Part 5 to `01-contracts-02.md`. That edit is uncommitted.
- `feat/01-evidence` is checked out. PR #3 (finding_key) and the evidence PR are
  not merged yet.
- Part 5 imports `SourceId` and `DataGroup` from `common/evidence.py`, so it has
  to stack on the evidence branch.

There are no hand-written files, no new dependencies and no fixtures. Part 5
does not read the trust matrix.

## 0. Branch and save this plan

- `git switch -c feat/01-search-plan` from `feat/01-evidence`. The PR's base is
  `feat/01-evidence` until that merges, then `main`. The spec edit comes with it.
- Copy this plan to `docs/plan/2026-11-25-day2-search-plan.md`.

## 1. Tests first: `common/tests/test_contracts.py`

Add a `# --- Part 5: search plan ---` section:
- `_task(**overrides)` builds the example's `nppes:identity` task.
- `_plan(**overrides)` builds the spec example: four requested fields, one task,
  and `office_hours` unplanned with reason NO_TRUST_ROWS.
- The trust weights in the tests are example data only, not real trust-matrix values.
- Acceptance cases 1-18 are named `test_s01_...` to `test_s18_...`.
  - Errors expect `ValidationError`, with `match=` where the spec names a reason:
    - "not accounted for"
    - "no trust rows"
    - "duplicate task"
    - `must be 'nppes:identity'`
    - "secrets not allowed"
  - 14: `plan.tasks_for_field("gender") == (the nppes:identity task,)`.
  - 15: three tasks in a given order: nppes:identity, caqh:attestation and
    provider_website:location. Each has fields that are COVERED and match its group.
  - 16: `SearchPlan.model_validate_json(p.model_dump_json()) == p`.
  - 17: `plan.tasks[0].fields = (...)` raises `ValidationError`.

Extra tests for rules that no numbered case covers:
- Rule 1: a short npi or an empty plan_version is refused.
- Rule 2: an unknown requested field and a duplicate requested field are both refused.
- Rule 3: an unplanned field that was not requested, and a field listed twice in
  unplanned_fields, are both refused.
- Rule 5: a task with empty fields, or with the same field twice, is refused.
- Rule 7: an extra weight entry for a field not in the task is refused. A
  weight of exactly 1 is valid.
- Rule 8: an empty key or an empty value in search_params is refused.
- Rule 9:
  - Parametrized over `api_key`, `TOKEN`, `client_secret` and `db_password`,
    upper and lower case: each is refused.
  - The error text never contains the secret value (see `hide_input_in_errors` below).
- `trust_weights["gender"] = 1.0` and `search_params["npi"] = "x"` raise
  `TypeError` (read-only mappings).
- `plan.task(SourceId.NPPES, DataGroup.IDENTITY)` returns the task. Asking for
  a missing pair raises `KeyError`.
- A DISCOVERY-origin task and a SkippedSource with a detail text are valid.
- An extra key on a plan or a task is refused.

Run `uv run pytest common` and show that the new tests fail before writing code.

## 2. Implementation: `common/search_plan.py`

- StrEnums with explicit upper-case values:
  - `CaseType`: TARGETED, COVERAGE
  - `TaskOrigin`: TRUST_MATRIX, DISCOVERY
  - `SkipReason`: INACTIVE_ROW, NOT_ALLOWED, NO_SEARCH_INPUT, DUPLICATE, OUT_OF_COVERAGE
  - `UnplannedReason`: NO_TRUST_ROWS, NO_ALLOWED_SOURCE
- Every model uses `ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)`.
  `hide_input_in_errors` keeps a refused `api_key` value out of error text,
  logs and traces.
- `Npi` and `NonEmptyStr` are reused from `common/evidence.py`. That file is not changed.
- Two helpers build read-only mappings:
  - `_frozen_mapping` is a field validator that wraps a dict in
    `MappingProxyType`, so `trust_weights` and `search_params` cannot be changed.
  - Type: `Mapping[str, float]` / `Mapping[str, str]`.
  - At implementation, check that JSON round-trip and equality still hold. If
    they don't, fall back to plain dicts and tell you.
- `SourceTask` has these fields:
  - `task_id`, `source_id`, `data_group` and `origin`
  - `fields: tuple[str, ...]` (min 1)
  - `trust_weights: Mapping[str, Annotated[float, Field(gt=0, le=1)]]`
  - `search_params: Mapping[NonEmptyStr, NonEmptyStr]` (min 1)

  An after-validator enforces:
  - rule 5: fields are unique
  - rule 6: task_id must be `f"{source_id.value}:{data_group.value.lower()}"`
  - rule 7: the weight keys equal the field set
  - rule 9: secret words, matched without regard to case, are refused. The
    error names only the key, never the value.
- `SkippedSource` has `source_id`, `data_group`, `reason: SkipReason` and
  `detail: str | None`.
- `UnplannedField` has `field_name` and `reason: UnplannedReason`.
- `SearchPlan` has these fields:
  - `case_id`, `npi`, `case_type`
  - `gold_version`, `trust_matrix_version`, `plan_version`
  - `requested_fields: tuple[str, ...]` (min 1)
  - `tasks: tuple[SourceTask, ...]`
  - `skipped_sources: tuple[SkippedSource, ...]`
  - `unplanned_fields: tuple[UnplannedField, ...]`

  An after-validator enforces:
  - rule 2: each requested field is known (via `get_field`) and unique
  - rule 4: each task field is requested and COVERED, otherwise "no trust rows"
  - rule 6: no two tasks share a (source_id, data_group), otherwise "duplicate task"
  - rule 3: each requested field is in a task or in unplanned, never both and
    never neither, otherwise "not accounted for". Unplanned names must be
    requested and unique.
  - rule 10: a skipped pair is not also a task
- Helpers:
  - `tasks_for_field(name)` returns a tuple of tasks in plan order, empty if none.
  - `task(source_id, data_group)` returns the task, or raises `KeyError`.
- `__all__`, type hints and docstrings. Tuples keep the order (rule 11). The
  file does not choose or reorder sources.

Points to confirm in review:
- `task()` raises `KeyError` when the pair is missing. It does not return None.
- The file does not check that an UnplannedField's reason matches the catalog
  (NO_TRUST_ROWS means PENDING_MENTOR), because the spec gives that only as a
  description, not a rule. It is easy to add if wanted.

## 3. Checks

`uv run pytest`, `uv run ruff check .`, `uv run mypy .`, and `ruff format`
on the touched files must all pass.

## 4. Close-out

- `01-contracts-02.md` Part 5: tick the first three tasks and the plan.md one,
  leave "Teammate reviews" open, and add a line to "Notes for the next session".
- `docs/plan.md`: tick `common/search_plan.py` and add one session-log line.
- Commit, push and give you the PR link and body only when you say so.

## Files

- New: `docs/plan/2026-11-25-day2-search-plan.md`
- Changed: `common/search_plan.py`, `common/tests/test_contracts.py`,
  `docs/specs/01-contracts-02.md`, `docs/plan.md`
- Reused:
  - `get_field` and `Coverage` from `common/field_catalog.py`
  - `SourceId`, `DataGroup`, `Npi` and `NonEmptyStr` from `common/evidence.py`

## Verification

- `uv run pytest common -v`: Parts 1-5 all pass, with the 18 acceptance cases
  plus the extras.
- `uv run mypy .` passes in strict mode, and `uv run ruff check .` is clean.
- `uv run python -c "from common.search_plan import SourceTask; print(SourceTask.model_json_schema()['properties'].keys())"`
