# Day 2 session plan: 01 - contracts, Part 6 `common/validation_report.py` (2026-11-25)

## Context

The schema-7 Validation Report is the contract between the agent (which
writes it) and the portal (which builds the review screen only from it). It
has to refuse anything ambiguous instead of guessing. Spec:
`docs/specs/01-contracts-02.md`, Part 6. Today `common/validation_report.py`
holds only a docstring. Part 6 is the last contract, so it closes Phase 1.

The repo is in this state:
- You added Part 6 to the spec. That edit is uncommitted.
- `feat/01-search-plan` is checked out. The finding-key, evidence and
  search-plan PRs are all unmerged.
- Part 6 uses `finding_key.py` and `evidence.py`, so it stacks on the tip of the chain.

Decisions you made today:
- **Fixture:** Claude drafts `sample_report.json` with made-up values, and you
  check it against the rules before any test is written.
- **Totals:** they are computed from the entries and written to JSON. On load,
  any totals given must equal the computed ones, otherwise the report is
  refused. So test 25's `9` is refused, and a JSON round-trip still works.
- **conflicts:** a tuple of `ConflictRef(field, representation)` for entries
  whose status is DISCREPANCY or FATAL_FLAW, in report order.

There are no new dependencies. Pydantic is 2.14, which supports `serialize_by_alias`.

## 0. Branch and save this plan

- `git switch -c feat/01-validation-report` from `feat/01-search-plan`. The PR's base is
  `feat/01-search-plan` until that merges. The spec edit comes with it.
- Copy this plan to `docs/plan/2026-11-25-day2-validation-report.md`.

## 1. Draft the fixture, then STOP for your check

`common/tests/fixtures/sample_report.json` uses made-up values only and
nothing from the seed CSVs:
- NPI `1000000004`
- representation `"HPHC"`
- two offices:
  - `PL-0001` (from Gold)
  - `addr:22 elm st|springfield ma 01103` (found only in evidence)
- phone numbers in the fictional 555 range

| # | Entry (in this order) | Mode | Entry status | Rows |
|---|---|---|---|---|
| 1 | degree | ONE_TO_ONE | CONFIRMED | `degree:provider`: MATCHED / CONFIRMED / VALUE_MATCH, sources CAQH and NPPES, scored with all 5 factors |
| 2 | practice_locations | SET | CANNOT_BE_VERIFIED | `…:PL-0001`: CONFIRMED / VALUE_MATCH. `…:addr:22 elm…`: ONLY_IN_EVIDENCE / CANNOT_BE_VERIFIED / NOT_CORROBORATED, no recommended value, not scored |
| 3 | phone | BY_LOCATION | DISCREPANCY | `phone:PL-0001`: VALUE_MISMATCH / DISCREPANCY / VALUE_MISMATCH with a recommended value. `phone:addr:22 elm…`: MISSING_VALUE / CANNOT_BE_VERIFIED / NOT_REPORTED_FOR_LOCATION |

This gives totals of 3 validations, 1 conflict (phone/HPHC) and 5 rows. The
fixture holds no totals, so they come only from the entries. I'll show you the
file and wait for your OK, or your edits, before step 2.

## 2. Tests first: `common/tests/test_contracts.py`

Add a `# --- Part 6: validation report ---` section:
- `_sample()` returns a fresh `dict` loaded from the fixture.
- `_load(d)` returns `ValidationReport.model_validate(d)`.
- Each bad-report test copies the sample, breaks one thing, and expects a
  `ValidationError`. Where the spec names a reason, it uses `match=` with the
  entry label, e.g. `"degree/HPHC"` (rule 19).
- Acceptance cases 1-25 are named `test_r01_...` to `test_r25_...`.
  - 22: `report.finding_keys()` gives 5 keys in report order, and each
    `row_id()` equals its row's `validation_row_id`.
  - 23: `model_validate_json(model_dump_json()) == report`.
  - 25: a typed-in `total_conflicts: 9` is refused. The correct value, `1`, is accepted.

Extra tests for rules that no numbered case covers:
- Rule 1: a short NPI, an empty `trust_matrix_version` or a naive `validated_at` is refused.
  `validated_at` is stored in UTC.
- Rule 3: `conflicts` equals `(ConflictRef("phone", "HPHC"),)`. A FATAL_FLAW
  entry also counts as a conflict.
- Rule 4: a `schema` of 6 is refused, and the JSON key is `"schema"`.
- Rule 6: an entry with no rows, or with two rows that share a row id, is refused.
- Rule 11: a SET row whose id does not match its location_group_id is refused.
- Rule 12: a non-`addr:` row whose `directory_location_id` differs from its group is refused.
- Rule 13: FATAL_FLAW accepts any reason code.
- Rule 15: `scored=True` with `score=None` is refused.
- Rule 16: a factor of 1.2, and an unknown sixth factor, are both refused.
- A second representation `"REP_B"` with only a degree entry is valid, since
  rule 9 applies to each representation separately.
- A `location_group_id` of `"provider"` or `"addr:"` on a location row is
  refused, because a FindingKey can't be built from it.
- Extra keys, such as the old `conflict_flag` on an entry, are refused.

Run `uv run pytest common` and show that the new tests fail before writing code.

## 3. Implementation: `common/validation_report.py`

- StrEnums:
  - `ValidationStatus`, `ComparisonType` and `ReasonCode` as in the spec.
  - `ALLOWED_REASONS: Mapping[ValidationStatus, frozenset[ReasonCode]]` holds
    the spec table, read-only. FATAL_FLAW maps to every reason code.
- Every model is frozen and refuses extra keys.
- Reused:
  - `Npi` and `NonEmptyStr` from `common/evidence.py`
  - `SourceId`, `DataGroup` and `QualityLabel` from `common/evidence.py`
  - `get_field`, `ComparisonMode` and `UnknownField` from `common/field_catalog.py`
  - `FindingKey` and `PROVIDER_SCOPE` from `common/finding_key.py`
- Small models:
  - `LocationContext` has `display_address`, `location_name` and `practice_location_id`.
  - `EvidenceLocationRef` has `source_id` and `source_location_id`. The spec
    calls it `LocationRef`, but I renamed it so it can't be mixed up with
    `evidence.LocationRef`, which has a different shape. To confirm in review.
- `Confidence` has these fields:
  - `scored: bool`
  - `score: float | None`
  - `action: str`, plain text until the mentor answers question 3
  - `factors: Mapping[str, float] | None`
  - `penalties: Mapping[str, float] | None`

  It enforces rules 15 and 16. The factor keys must be exactly the five
  names, each in [0, 1]. The mappings are read-only, with a dict serializer
  (the same pattern as `search_plan.py`).
- `SourceSummary` has these fields:
  - `source_id`, `value: str | None` and `url` (non-empty)
  - `data_group`, `quality_label`, `source_last_update: date | None`
  - `retrieved_at`, aware and stored in UTC
  - `matches_directory: bool | None` and `status_detail: str | None`
- `ValidationRow` holds the spec's fields. It checks the rules that need only
  the row itself:
  - rule 12
  - rule 13: reason against status
  - rule 14: CANNOT_BE_VERIFIED has no recommended value, and DISCREPANCY
    needs a non-empty one
- `ValidationEntry` has these fields:
  - `schema_version: Literal[7] = Field(7, alias="schema")`, with
    `validate_by_name` and `serialize_by_alias` so the JSON key is `schema`.
    A field called `schema` would shadow `BaseModel.schema`.
  - `field`, `representation`, `comparison_mode`, `data_group`, `status`
    and `rationale`
  - `sources`, a tuple
  - `validation_rows`, a tuple with at least one row

  It checks rules 4-8 and 11, and builds a FindingKey for every row. Every
  message starts with `entry <field>/<representation>: rule N:`.
- `ValidationReport` has these fields:
  - `report_id`, `case_id`, `practitioner_npi`, `validated_at` (UTC)
  - `gold_version`, `trust_matrix_version` and `validations`

  Totals:
  - `total_validations`, `total_conflicts` and `conflicts` are `@computed_field`
    properties, so they are written to JSON.
  - A `model_validator(mode="before")` removes any of these keys from the
    input. It keeps their values, and the after-validator compares them with
    the computed ones (rule 3 and test 25).

  The after-validator checks:
  - rule 2: one entry per (field, representation)
  - rule 9: each representation that has a BY_LOCATION entry has a
    practice_locations SET entry, placed before all of its BY_LOCATION entries
  - rule 10: every BY_LOCATION row's group is in that SET entry, with an
    identical `location_context`

  `finding_keys()` returns a tuple of FindingKey, one per row, in report order.
- Rule 19: each validator raises at the first problem, with one message. It
  never drops or repairs part of the input.

Points to confirm in review:
- The rename to `EvidenceLocationRef`.
- How I read rule 9: the SET entry must come before every BY_LOCATION entry of
  its representation. A ONE_TO_ONE entry like degree may still come first.
- SET and BY_LOCATION rows need a `location_group_id`. The `location_context`
  stays optional, and rule 10 compares it as it is.

## 4. Checks

`uv run pytest`, `uv run ruff check .`, `uv run mypy .`, and `ruff format`
on the touched files must all pass.

## 5. Close-out (this ends Phase 1)

- Part 6 tasks in the spec: tick everything except "Teammate reviews", and add
  a line to "Notes for the next session".
- `docs/plan.md`:
  - Tick `common/validation_report.py`.
  - Update "Now": the phase becomes 2 (walking skeleton), and the next task
    is `02-skeleton.md`.
  - Add one session-log line.
- `CLAUDE.md`: change "Current phase" to Phase 2.
- Commit, push and give you the PR link and body only when you say so.

## Files

- New:
  - `common/tests/fixtures/sample_report.json` (you check it)
  - `docs/plan/2026-11-25-day2-validation-report.md`
- Changed:
  - `common/validation_report.py`
  - `common/tests/test_contracts.py`
  - `docs/specs/01-contracts-02.md`
  - `docs/plan.md` and `CLAUDE.md` (phase lines only)

## Verification

- `uv run pytest common -v`: Parts 1-6 all pass, with the 25 acceptance cases
  plus the extras.
- `uv run mypy .` passes in strict mode, and `uv run ruff check .` is clean.
- `uv run python -c "import json, pathlib; from common.validation_report import ValidationReport as R; r = R.model_validate_json(pathlib.Path('common/tests/fixtures/sample_report.json').read_text()); print(r.total_validations, r.total_conflicts, [k.row_id() for k in r.finding_keys()])"`
  prints `3 1` and the 5 row ids.
