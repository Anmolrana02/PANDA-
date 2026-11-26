# `common/` notes: the shared contracts

`common/` holds the contracts that both owners depend on. The agent plane
(Anmol) writes these objects and the portal plane (teammate) reads them. **Do
not change anything here unless both owners agree.**

Specs: `docs/specs/01-contracts-01.md` (Parts 1-3) and
`docs/specs/01-contracts-02.md` (Parts 4-6). The specs are the source of
truth. This file is a reading guide. Last updated 2026-11-25.

## The six files at a glance

| Part | File | What it answers | Depends on |
|---|---|---|---|
| 1 | `states.py` | Which status can follow which? | nothing |
| 2 | `field_catalog.py` | What are the 29 audit fields, and how is each compared? | nothing |
| 3 | `finding_key.py` | What is the unique name of one finding? | field_catalog |
| 4 | `evidence.py` | What did one source say, and where and when? | field_catalog |
| 5 | `search_plan.py` | Which sources to ask for which fields, in what order? | field_catalog, evidence |
| 6 | `validation_report.py` | The schema-7 report the portal reads | field_catalog, finding_key, evidence |

How they fit together, following one case:

```
states.AgentCaseState:  CREATED -> PLANNED -> RETRIEVING -> VALIDATING -> SCORING -> ROUTING -> CLOSED / HITL_PENDING
                                     |            |              |
                               SearchPlan   EvidenceBundle(s)  ValidationReport
                              (search_plan)    (evidence)    (validation_report)
                                                                   |
                                                    finding_keys() -> FindingKey per row
                                                    (reviewer decisions are stored under it)
```

Everything is checked against `field_catalog.py`. No other file types out field names.

## Shared conventions (all six files)

- **Pydantic v2 models are frozen and refuse extra keys.** You cannot change
  an object after it's made. Assigning a field raises `ValidationError`.
  Unknown keys, such as an old `conflict_flag`, are refused.
- **Statuses and vocabularies are `StrEnum`s whose values are their upper-case
  names**, such as `"CONFIRMED"`. The exception is `SourceId`, whose values
  are lower case (`"nppes"`). They save to JSON and databases as plain text.
- **Read-only tables** (move tables, `ALLOWED_REASONS`) are `MappingProxyType`.
  Mapping fields inside models (`trust_weights`, `search_params`,
  `Confidence.factors` and `penalties`) are also read-only. A
  `field_serializer` writes them as plain dicts, because Pydantic can't
  serialize `MappingProxyType`.
- **Times must include a time zone.** A time without one is refused, and
  every time is stored in UTC.
- **An NPI is text of exactly 10 digits**, so leading zeros are kept.
- **Errors never guess.** A bad input raises one error naming what is wrong.
  Nothing is skipped, trimmed or repaired.
- **Every model round-trips through JSON:**
  `Model.model_validate_json(x.model_dump_json()) == x`.

## Part 1: `states.py`

There are three separate state machines, each with one read-only move table:

- `AgentCaseState`, for one NPI investigation:
  - CREATED → PLANNED → RETRIEVING → VALIDATING → SCORING → ROUTING → CLOSED or HITL_PENDING
  - Any non-final state can move to CANCELLED.
  - Final states: CLOSED, HITL_PENDING and CANCELLED.
- `DispatchState`, for handing a case to the graph:
  - PENDING → DISPATCHING → DONE, PENDING (retry) or EXHAUSTED.
  - Final states: DONE and EXHAUSTED.
- `PortalBatchState`, for a reviewer batch:
  - OPEN → ASSIGNED → IN_PROGRESS → REVIEWER_DECIDED → CLOSED or EXPERT_REVIEW → CLOSED.
  - These statuses were confirmed by both owners.

Functions: `allowed_moves(s)`, `is_final(s)`, `can_transition(a, b)` and
`require_transition(a, b)`, which raises `InvalidTransition`.

**Gotcha:** StrEnum members compare equal by text, so
`AgentCaseState.CLOSED == PortalBatchState.CLOSED`. Mixing machines therefore
raises `TypeError`, and plain strings are refused. Keep the enum type, never a
bare string.

## Part 2: `field_catalog.py`

There are 29 `FieldSpec`s, in `Audit Fields.txt` order. Each has:
- `name`
- `level`: PROVIDER or LOCATION
- `mode`: ONE_TO_ONE, SET or BY_LOCATION
- `gold_columns` and `trust_fields`
- `coverage`: COVERED or PENDING_MENTOR

Lookups:
- `get_field(name)` raises `UnknownField`.
- `all_fields()`, `provider_fields()`, `location_fields()` and
  `covered_fields()` each return a tuple in catalog order.

Key facts:
- 13 fields are COVERED, meaning they have trust-matrix rows. 16 are
  PENDING_MENTOR. Coverage is COVERED if and only if `trust_fields` is not empty.
- The mode follows the level:
  - PROVIDER fields are ONE_TO_ONE.
  - LOCATION fields are BY_LOCATION.
  - The only exception is `practice_locations`, which is **SET**.
- `specialty` uses the trust matrix's spelling: `primary_speciality` and
  `additional_specialities`.
- Four fields have no Gold column yet: network_participation, license_status,
  license_number and expiration_date.
- `IGNORED_TRUST_FIELDS = {"npi", "hospital_admitting_privileges"}`: trust names
  that belong to no audit field.
- Gold has look-alike columns the catalog doesn't use, such as
  `provider_specialty` and `provider_role`.

## Part 3: `finding_key.py`

`FindingKey(field_name, representation, location_key)` names one finding.
Reviewer decisions, field history and rationale are stored under it.

- Constructors: `FindingKey.for_provider(field, rep)` and
  `FindingKey.for_location(field, rep, loc)`. The positional form
  `FindingKey("degree", "HPHC", "provider")` also works.
- Location key rules:
  - A PROVIDER field uses `PROVIDER_SCOPE = "provider"`.
  - A LOCATION field uses either a Gold `practice_location_id` or
    `"addr:<text>"`, which means the office was found only in evidence.
- Nothing is trimmed or lower-cased, so `" HPHC" != "HPHC"`. "HPHC" is never
  hard-coded.
- Methods:
  - `row_id()` returns `"<field>:<location_key>"`, which is the report's `validation_row_id`.
  - `is_provider_scope()` and `is_reported_only()`, which is True for an `addr:` key.
- `to_str()` / `from_str()` store the key as a JSON list of 3 parts, so `:` and
  `|` are safe. `from_str` raises `ValueError` on anything else.
- The key works in sets and as a dict key, because equal keys have the same hash.

**Gotcha:** Pydantic routes `model_validate` through a custom `__init__`. So
`__init__` passes `**extra` on to Pydantic, which keeps `extra="forbid"` working.

## Part 4: `evidence.py`

- `EvidenceAssertion` is one fact: one field, from one source, and for
  location fields one office (`LocationRef`).
  - `raw_value` is kept exactly as the source gave it, up to 2,000 characters,
    because a whole web page is never a value. `normalized_value` is filled in
    later by validation and may be None.
  - Status:
    - FOUND needs a non-empty `raw_value`.
    - NO_VALUE, NOT_FOUND, UNAVAILABLE and AMBIGUOUS must have no values.
  - A FOUND location field needs a `location_ref`. A provider field never has one.
  - `url_or_identifier` is always filled, even for a failure: it holds the URL that was tried.
  - `status_detail` is free text from the source. Nothing makes decisions from it.
  - It holds no conclusions: no match, no score and no route.
- `EvidenceBundle` holds all assertions from one source and one data group for one case.
  - It needs at least one assertion, kept in order. A failed source returns
    UNAVAILABLE assertions, never an empty bundle.
  - Each assertion's case_id, npi, source_id and data_group must equal the
    bundle's. A mismatch is refused as "mixed sources".
- Vocabulary:
  - `SourceId`: caqh, nppes, provider_website and google_search. Its
    `.trust_matrix_name` gives "CAQH", "NPPES", "Provider Website" and "Google
    Searches". Test 14 checks these against the trust matrix fixture.
  - `DataGroup`: IDENTITY, ATTESTATION and LOCATION.
  - `AssertionStatus` and `QualityLabel` (STATED or TRANSFORMED).
- Reusable types: `NonEmptyStr` and `Npi` are imported by Parts 5 and 6.

To confirm in review: `raw_value` is text, so a source that returns a list stores its text as given.

## Part 5: `search_plan.py`

- `SearchPlan` is the to-do list for one case. It holds:
  - `requested_fields`
  - `tasks`, kept in the planner's order so a replay gives the same report
  - `skipped_sources` and `unplanned_fields`
- `SourceTask` covers one (source, data group) and produces one EvidenceBundle.
  - `task_id` must be exactly `"<source_id>:<data_group lower>"`, e.g. `nppes:identity`.
  - `fields` must be unique.
  - `trust_weights` has exactly one entry per field, each in (0, 1].
  - `search_params` must not be empty.
  - `origin` is TRUST_MATRIX or DISCOVERY.
- Every requested field is in a task or in `unplanned_fields`, never both and never neither.
- Task fields must be requested and COVERED. A PENDING_MENTOR field is refused
  as "no trust rows".
- No two tasks may share a (source, group), and a skipped pair can't also be a task.
- **No secrets:** a `search_params` key containing key, token, secret or
  password (any case) is refused. The error names only the key, and
  `hide_input_in_errors` keeps the value out of errors, logs and traces.
- Helpers:
  - `plan.tasks_for_field(name)` returns the tasks in order.
  - `plan.task(source, group)` returns the task, or raises `KeyError`.
  - `task_id_for(source, group)` builds a task_id.

To confirm in review:
- `task()` raises `KeyError` rather than returning None.
- An UnplannedField's reason is not checked against the catalog.

## Part 6: `validation_report.py`

This is the report the portal builds its review screen from. It holds:

- `ValidationReport`:
  - `report_id`, `case_id`, `practitioner_npi`, `validated_at`
  - `gold_version`, `trust_matrix_version`
  - `validations`, a tuple of entries
- `ValidationEntry`, one per (field, representation):
  - `schema = 7`
  - `field`, `representation`, `comparison_mode`, `data_group`
  - `status` and `rationale`
  - `sources`, a tuple of `SourceSummary`
  - `validation_rows`, a tuple of `ValidationRow`
- `ValidationRow`, one comparison:
  - row ids and location fields
  - `comparison_type`
  - `gold_value`, `evidence_value` and `recommended_value`
  - `validation_status` and `reason_code`
  - `evidence_sources`
  - `confidence`

Totals:
- `total_validations`, `total_conflicts` and `conflicts` are computed
  properties and are written to JSON.
- `conflicts` is a list of `ConflictRef(field, representation)` for entries
  whose status is DISCREPANCY or FATAL_FLAW.
- Totals given in an input must equal the computed ones, or the report is refused.

Main rules (the spec numbers 19):
- One entry per (field, representation).
- `comparison_mode` must equal the catalog's mode.
- A ONE_TO_ONE entry has exactly one row, with no location fields and id
  `"<field>:provider"`.
- SET and BY_LOCATION rows:
  - They need a `location_group_id`, and the row id is `"<field>:<group>"`.
  - An `addr:` group has no `directory_location_id`. Any other group has
    `directory_location_id == group`.
- Within a representation:
  - If there is any BY_LOCATION entry, the `practice_locations` SET entry must
    come before it.
  - Each BY_LOCATION row's group, and its `location_context`, must match the SET entry's.
- Reason codes must fit the status, from the `ALLOWED_REASONS` table. FATAL_FLAW allows any reason.
- Recommended value: CANNOT_BE_VERIFIED rows have none, and DISCREPANCY rows must have one.
- `Confidence`:
  - When scored, the score is in [0, 1]. When unscored, the score is None.
  - If factors are given, they are exactly authority, recency, quality,
    reliability and corroboration, each in [0, 1].
  - `action` stays plain text until the mentor answers question 3.
- `report.finding_keys()` gives one `FindingKey` per row, in report order. Every
  row's key is built when the report loads, so a bad location key fails early.
- Error messages read `entry <field>/<rep>: rule N: …`.

**Gotcha:** a field named `schema` shadows `BaseModel.schema`. So it is
`schema_version`, with alias `"schema"` and `serialize_by_alias`, and the JSON
key is still `"schema"`.

To confirm in review:
- The spec's `LocationRef` is renamed `EvidenceLocationRef`.
- How I read rule 9: the SET entry comes before every BY_LOCATION entry of its
  representation.
- Confidence errors name the entry by position, not by its label.

## Tests and fixtures

- All contract tests are in `common/tests/test_contracts.py`, one section per
  part. The test names show the part:
  - `test_01..` for states
  - `test_c..` for the field catalog
  - `test_k..` for the finding key
  - `test_e..` for evidence
  - `test_s..` for the search plan
  - `test_r..` for the validation report
  - extra rule tests as `test_rule..`, `test_key_..`, `test_ev_..`, `test_sp_..` and `test_rp_..`
- `common/tests/fixtures/` holds names only, generated from the seed CSVs with
  `load_seed.py`, so tests work in CI without the gitignored CSVs:
  - `gold_columns.txt`: 46 Gold column names
  - `trust_field_names.txt`: 21 trust-matrix field names
  - `trust_source_systems.txt`: 4 source names
- `sample_report.json` is a hand-built report with made-up values:
  - NPI `1000000004`
  - offices `PL-0001` and `addr:22 elm st|springfield ma 01103`
  - entries for degree, practice_locations and phone
  - Every bad-report test copies it and breaks one thing.
- Run them with `uv run pytest common`. On 2026-11-25, 360 tests passed.

## Status and branches (2026-11-25)

All six parts are coded and waiting on teammate review. The PRs are stacked,
so merge them from the bottom up and retarget the next PR's base to `main`
after each merge:

```
main <- feat/01-states (merged, PR #2: states + field_catalog)
     <- feat/01-finding-key (PR #3) <- feat/01-evidence <- feat/01-search-plan <- feat/01-validation-report
```

Open questions for the review are collected under each part above and in the
specs' "Notes for the next session".
