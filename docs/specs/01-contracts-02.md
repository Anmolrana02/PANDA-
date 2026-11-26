# Feature spec: 01 - contracts (file 2 of 2)

Owner: Anmol Rana + Harsh Giri (common/ is shared). Phase in plan.md: 1.
Parts 1-3 (states, field_catalog, finding_key) are in 01-contracts-01.md.
This file holds Parts 4-6.
Uses: common/field_catalog.py, common/finding_key.py.

---

## Part 4 - common/evidence.py

Status: draft.
Uses: common/field_catalog.py (field names and levels).

## Goal

Give every source adapter one fixed shape for "what a source said", so the
validator can compare any source with Gold, and every value can be traced
back to where and when it was found.

## Inputs and outputs

- Input: what an adapter found for one field of one provider.
- Output 1: an EvidenceAssertion (one fact, one field, one source, and for
  location fields one office). Example:

      case_id="CASE-637551BD11B2", npi="1013489194", field_name="degree",
      data_group=IDENTITY, source_id=NPPES,
      raw_value="LMHC", normalized_value=None,
      status=FOUND, status_detail=None,
      url_or_identifier="https://npiregistry.cms.hhs.gov/api/?number=1013489194&version=2.1",
      retrieved_at=2026-11-09T22:35:07Z, source_last_update=2024-03-04,
      quality_label=STATED, adapter_version="nppes-0.1", location_ref=None

- Output 2: an EvidenceBundle (all assertions from one source and one data
  group for one case), with case_id, npi, source_id, data_group,
  gold_version, trust_matrix_version, correlation_id, created_at,
  assertions.

## Vocabulary (StrEnums in this file)

- SourceId: CAQH="caqh", NPPES="nppes", PROVIDER_WEBSITE="provider_website",
  GOOGLE_SEARCH="google_search"
  Each one knows its trust-matrix name: "CAQH", "NPPES",
  "Provider Website", "Google Searches".
- DataGroup: IDENTITY, ATTESTATION, LOCATION
- AssertionStatus:
  - FOUND - the source gave a usable value
  - NO_VALUE - the source has the provider, but this field is empty
  - NOT_FOUND - the source has no record of the provider
  - UNAVAILABLE - the source could not be reached or returned an error
  - AMBIGUOUS - the source matched more than one provider or office
- QualityLabel: STATED (the source said it directly),
  TRANSFORMED (we reshaped it, e.g. split an address)

LocationRef (for location fields only): display_address (as the source
wrote it), location_name (optional), practice_location_id (optional, only
if the source gave one).

## Rules

1. field_name must be one of the 29 fields in field_catalog.py.
2. npi is text of exactly 10 digits.
3. status FOUND needs a non-empty raw_value. Every other status needs
   raw_value and normalized_value to be None.
4. raw_value is kept exactly as the source gave it. Nothing in the system
   overwrites it; normalized_value is filled in later (validation phase)
   and may be None until then.
5. raw_value is at most 2,000 characters. Web text is untrusted data, and a
   whole page must never be stored as a value.
6. url_or_identifier is always filled, even when the status is NOT_FOUND or
   UNAVAILABLE (e.g. the URL that was tried).
7. retrieved_at must include a time zone; it is stored in UTC.
   source_last_update is a date and may be None.
8. A FOUND assertion for a LOCATION field must have a location_ref.
   A PROVIDER field must not have one.
9. status_detail is optional free text for the source's own code
   (e.g. "NOT_IN_EXTRACT", "NO_MATCH"). Nothing may make decisions from it.
10. An assertion holds no conclusions: no "matches directory", no score,
    no route.
11. Assertions and bundles are frozen once made.
12. Every assertion in a bundle has the same case_id, npi, source_id and
    data_group as the bundle.
13. A bundle has at least one assertion. A source that failed returns
    UNAVAILABLE assertions instead of an empty bundle, so the failure stays
    visible.
14. A bundle keeps its assertions in the order given.
15. gold_version and trust_matrix_version are non-empty on every bundle.
16. Assertions and bundles turn into JSON and back without losing anything.

## Out of scope

- Fetching evidence (adapters, Phase 3)
- Normalizing values (Phase 4)
- Deciding whether evidence matches Gold (validator)
- Scoring factors such as recency or corroboration (Phase 5)
- Which sources to ask for which fields (search_plan.py, next spec)

## Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | the NPPES degree example above | make the assertion | valid |
| 2 | status FOUND, raw_value "" | make it | error |
| 3 | status NOT_FOUND, raw_value "LMHC" | make it | error: no value allowed |
| 4 | status NOT_FOUND, no value, status_detail "NOT_IN_EXTRACT" | make it | valid |
| 5 | npi "12345" | make it | error |
| 6 | npi "0123456789" | make it | valid, leading 0 kept |
| 7 | field_name "fax" | make it | error: unknown field |
| 8 | raw_value of 2,001 characters | make it | error |
| 9 | retrieved_at without a time zone | make it | error |
| 10 | FOUND phone with no location_ref | make it | error: location field needs an office |
| 11 | FOUND degree with a location_ref | make it | error: provider field has no office |
| 12 | url_or_identifier "" | make it | error |
| 13 | SourceId.GOOGLE_SEARCH | ask its trust-matrix name | "Google Searches" |
| 14 | every SourceId | look up its trust-matrix name | each matches a source_system in trust.csv |
| 15 | a bundle with one CAQH and one NPPES assertion | make it | error: mixed sources |
| 16 | a bundle with no assertions | make it | error |
| 17 | a bundle of 3 assertions | read them back | same order |
| 18 | any assertion | try to change raw_value | error (frozen) |
| 19 | a bundle | to JSON and back | equal to the original |
| 20 | a bundle with gold_version "" | make it | error |

## Files

- New: common/evidence.py
- Changed: common/tests/test_contracts.py (add tests 1-20)
- Hand-written by owner: none. The owner checks the rules; Claude Code
  writes the code.

## Tasks

- [x] Write failing tests for cases 1-20
- [x] Write common/evidence.py until they pass
- [x] ruff, mypy, pytest pass
- [ ] Teammate reviews (common/ is shared)
- [x] Tick "common/evidence.py" in docs/plan.md, add a session log line


---

## Part 5 - common/search_plan.py

### What it is

The to-do list for one case: which sources to ask for which fields, with
what search details, and what was skipped and why. The planner node writes
it; the evidence node follows it. One task in the plan produces one
EvidenceBundle (same source, same data group).

### Inputs and outputs

- Input: built by the planner (Phase 3); this part only defines the shape.
- Output: a frozen SearchPlan. Example:

      case_id="CASE-637551BD11B2", npi="1013489194", case_type=TARGETED,
      gold_version="gold-2026-11-01", trust_matrix_version=
        "client-v2.0-caqh-nppes-web-google-2026-10-21",
      plan_version="planner-0.1",
      requested_fields=("npi_type", "provider_name", "gender", "office_hours"),
      tasks=(
        SourceTask(
          task_id="nppes:identity", source_id=NPPES, data_group=IDENTITY,
          fields=("npi_type", "provider_name", "gender"),
          trust_weights={"npi_type": 0.85, "provider_name": 0.30,
                         "gender": 0.30},
          search_params={"npi": "1013489194"},
          origin=TRUST_MATRIX),
      ),
      skipped_sources=(),
      unplanned_fields=(UnplannedField(field_name="office_hours",
                                       reason=NO_TRUST_ROWS),)

- Helpers: plan.tasks_for_field(name), plan.task(source_id, data_group).

### Vocabulary (StrEnums in this file)

- CaseType: TARGETED (chosen providers), COVERAGE (a broad sweep)
- TaskOrigin: TRUST_MATRIX (the matrix allows this source),
  DISCOVERY (added to find a website when none is known)
- SkipReason: INACTIVE_ROW, NOT_ALLOWED, NO_SEARCH_INPUT, DUPLICATE,
  OUT_OF_COVERAGE (each skip also has optional detail text)
- UnplannedReason: NO_TRUST_ROWS (field is PENDING_MENTOR),
  NO_ALLOWED_SOURCE (every source for it was skipped)

SourceId and DataGroup come from common/evidence.py.

### Rules

1. case_id, gold_version, trust_matrix_version and plan_version are
   non-empty. npi is exactly 10 digits.
2. requested_fields is non-empty; every name is in field_catalog.py and
   appears only once.
3. Each requested field is either in at least one task, or in
   unplanned_fields - never both, never neither.
4. Every task field is in requested_fields, and every task field is
   COVERED in the field catalog.
5. A task's fields are non-empty and unique.
6. Only one task per (source_id, data_group). task_id is exactly
   "<source_id>:<data_group>", e.g. "nppes:identity".
7. trust_weights has exactly one entry per field in the task, and each
   weight is greater than 0 and at most 1.
8. search_params is non-empty; keys and values are non-empty text.
9. No secret ever goes in a plan (it is saved in checkpoints and traces):
   a search_params key containing "key", "token", "secret" or "password"
   is refused.
10. A skipped (source, data_group) is not also a task.
11. The order of tasks is kept exactly; evidence results are written in
    this order, so a replay gives the same report.
12. The plan is frozen and survives JSON and back unchanged.

### Out of scope

- Reading trust.csv and choosing sources (planner, Phase 3)
- Which search_params each adapter needs (adapters, Phase 3)
- Running the tasks or retrying them (evidence node)
- Deciding the task order (the planner decides; this file only keeps it)

### Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | the example above | make the plan | valid |
| 2 | gender in requested_fields but in no task and not unplanned | make it | error: field not accounted for |
| 3 | office_hours both in a task and in unplanned_fields | make it | error |
| 4 | a task with field office_hours (PENDING_MENTOR) | make it | error: field has no trust rows |
| 5 | a task field that is not in requested_fields | make it | error |
| 6 | two tasks with source NPPES and group IDENTITY | make it | error: duplicate task |
| 7 | task_id "nppes-identity" | make it | error: must be "nppes:identity" |
| 8 | trust_weights missing the gender entry | make it | error |
| 9 | trust weight 0 or 1.2 | make it | error |
| 10 | search_params {"api_key": "x"} | make it | error: secrets not allowed |
| 11 | search_params {} | make it | error |
| 12 | NPPES identity both skipped and a task | make it | error |
| 13 | requested_fields () | make it | error |
| 14 | the example plan | tasks_for_field("gender") | the nppes:identity task |
| 15 | 3 tasks in a given order | read them back | same order |
| 16 | the example plan | to JSON and back | equal to the original |
| 17 | any plan | try to change a task's fields | error (frozen) |
| 18 | a plan with no tasks and every field unplanned | make it | valid (everything becomes CANNOT_BE_VERIFIED later) |

### Files

- New: common/search_plan.py
- Changed: common/tests/test_contracts.py (add tests 1-18)
- Hand-written by owner: none. The owner checks the rules; Claude Code
  writes the code.

### Tasks

- [x] Write failing tests for cases 1-18
- [x] Write common/search_plan.py until they pass
- [x] ruff, mypy, pytest pass
- [ ] Teammate reviews (common/ is shared)
- [x] Tick "common/search_plan.py" in docs/plan.md, add a session log line

---

## Part 6 - common/validation_report.py

### What it is

The schema-7 Validation Report for one case: the contract between the agent
(which writes it) and the portal (which reads it). The portal builds the
review screen only from this report, so the report refuses anything
ambiguous instead of guessing (guide section 5.3).

Uses: field_catalog.py (FieldLevel, ComparisonMode), finding_key.py,
evidence.py (SourceId, DataGroup, QualityLabel).

### Shape

ValidationReport (one per case)
- report_id, case_id, practitioner_npi, validated_at (UTC)
- gold_version, trust_matrix_version   (our addition, for tracing)
- validations: tuple of ValidationEntry
- total_validations, total_conflicts, conflicts: worked out from
  validations, never typed in by hand

ValidationEntry (one field in one representation)
- schema = 7
- field, representation, comparison_mode, data_group
- status (the field's overall outcome), rationale (plain text)
- sources: tuple of SourceSummary
- validation_rows: tuple of ValidationRow

SourceSummary (what one source said, as shown to the reviewer)
- source_id, value, url, data_group, quality_label,
  source_last_update, retrieved_at, matches_directory (True/False/None),
  status_detail (optional)

ValidationRow (one comparison)
- validation_row_id, location_group_id, directory_location_id,
  location_context, evidence_location_refs
- comparison_type, gold_value, evidence_value, recommended_value
- validation_status, reason_code
- evidence_sources: tuple of SourceId
- confidence: Confidence

LocationContext: display_address, location_name, practice_location_id
LocationRef: source_id, source_location_id
Confidence: scored, score, action, factors (optional), penalties (optional)

Example row (from a real sample, values changed):

    validation_row_id="degree:provider", location_group_id=None,
    directory_location_id=None, location_context=None,
    evidence_location_refs=(), comparison_type=MATCHED,
    gold_value="LMHC", evidence_value="lmhc, other degree",
    recommended_value="LMHC", validation_status=CONFIRMED,
    reason_code=VALUE_MATCH, evidence_sources=(CAQH, NPPES),
    confidence=Confidence(scored=True, score=0.73, action="NO_CHANGE",
      factors={"authority": 0.85, "recency": 0.0, "quality": 1.0,
               "reliability": 0.8, "corroboration": 1.0})

### Vocabulary (StrEnums in this file)

- ValidationStatus: CONFIRMED, DISCREPANCY, CANNOT_BE_VERIFIED, FATAL_FLAW
- ComparisonType: MATCHED, VALUE_MISMATCH, MISSING_VALUE, ONLY_IN_GOLD,
  ONLY_IN_EVIDENCE
- ReasonCode (from the samples):
  VALUE_MATCH, VALUE_MISMATCH, NEW_EVIDENCE_VALUE, MISSING_DIRECTORY_VALUE,
  MISSING_EVIDENCE_VALUE, NO_VALUE, NOT_REPORTED_FOR_LOCATION,
  NOT_CORROBORATED
- Confidence.action stays plain text for now: three action vocabularies
  exist (mentor question 3). Make it an enum once he answers.

Which reason fits which status:

| Status | Allowed reason codes |
|---|---|
| CONFIRMED | VALUE_MATCH |
| DISCREPANCY | VALUE_MISMATCH, NEW_EVIDENCE_VALUE, MISSING_DIRECTORY_VALUE |
| CANNOT_BE_VERIFIED | NO_VALUE, MISSING_EVIDENCE_VALUE, NOT_REPORTED_FOR_LOCATION, NOT_CORROBORATED |
| FATAL_FLAW | any (FATAL_FLAW is a safety flag, not a comparison result) |

### Rules

Report
1. practitioner_npi is 10 digits; report_id, case_id, gold_version and
   trust_matrix_version are non-empty; validated_at has a time zone.
2. Only one entry per (field, representation).
3. total_validations = number of entries. conflicts = entries whose status
   is DISCREPANCY or FATAL_FLAW; total_conflicts = number of conflicts.

Entry
4. schema is 7; field is in the field catalog; representation is non-empty.
5. comparison_mode must equal the field's mode in the catalog. Only
   practice_locations is SET. (Note: some mentor samples use ONE_TO_ONE for
   a provider with one office; our reports always use BY_LOCATION for
   location fields, even with one row.)
6. An entry has at least one row; validation_row_id is unique inside it.
7. Every row's evidence_sources appear in the entry's sources.

ONE_TO_ONE
8. Exactly one row, with location_group_id, directory_location_id and
   location_context all None, and validation_row_id "<field>:provider".

SET and BY_LOCATION
9. A representation that has any BY_LOCATION entry must have a
   practice_locations SET entry, and the SET entry comes first in that
   representation.
10. Every BY_LOCATION row's location_group_id must appear in the SET entry
    of the same representation, and its location_context must equal the
    SET row's context for that group.
11. validation_row_id = "<field>:<location_group_id>".
12. If location_group_id starts with "addr:", directory_location_id is
    None. Otherwise directory_location_id equals location_group_id.

Rows
13. reason_code must be allowed for validation_status (table above).
14. CANNOT_BE_VERIFIED rows have recommended_value None. DISCREPANCY rows
    must have a recommended_value.
15. Confidence: scored True needs 0 <= score <= 1; scored False needs score
    None. A row's score is never copied from another row or the case.
16. If factors are given, the five keys authority, recency, quality,
    reliability and corroboration must all be there, each between 0 and 1.

Whole report
17. report.finding_keys() returns one FindingKey per row, in report order;
    each key's row_id() equals that row's validation_row_id.
18. The report is frozen and survives JSON and back unchanged.
19. A broken report raises one error that names the entry and the rule;
    it never skips the bad part and carries on.

### Out of scope

- How rows are worked out from evidence (validator, Phase 4)
- How row outcomes combine into the entry status (validator)
- How scores are calculated (scoring, Phase 5)
- Saving the report (ledger, Phase 5)
- The old sample fields: gold_value / evidence_value / match /
  conflict_flag / offices / office_result at entry level
- Reading the mentor's validation.csv (it is broken; waiting for a clean
  export)

### Sample report fixture

Hand-build common/tests/fixtures/sample_report.json with made-up values
(never copied from the seed CSVs): one provider, representation "HPHC",
two offices (one with a practice_location_id, one "addr:" only), and
entries for degree (CONFIRMED), practice_locations (SET, 2 rows) and phone
(BY_LOCATION: one DISCREPANCY, one CANNOT_BE_VERIFIED). Every bad-report
test starts from this file and breaks one thing.

### Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | the sample fixture | load it | valid |
| 2 | the sample | read totals | total_validations 3; total_conflicts 1 if phone's entry status is DISCREPANCY |
| 3 | an entry with field "fax" | load | error naming the entry |
| 4 | two degree entries in HPHC | load | error: duplicate entry |
| 5 | degree entry with mode BY_LOCATION | load | error: mode must be ONE_TO_ONE |
| 6 | phone entry with mode SET | load | error: only practice_locations may be SET |
| 7 | degree entry with two rows | load | error: ONE_TO_ONE needs exactly one row |
| 8 | degree row with a location_group_id | load | error |
| 9 | degree row id "degree:3038479374" | load | error: must be "degree:provider" |
| 10 | a phone entry but no practice_locations entry | load | error |
| 11 | phone entry placed before practice_locations | load | error: SET must come first |
| 12 | phone row with a group not in the SET entry | load | error |
| 13 | phone row whose location_context differs from the SET row | load | error |
| 14 | "addr:" row with a directory_location_id | load | error |
| 15 | CONFIRMED row with reason NO_VALUE | load | error |
| 16 | CANNOT_BE_VERIFIED row with a recommended_value | load | error |
| 17 | DISCREPANCY row with no recommended_value | load | error |
| 18 | scored True, score 1.4 | load | error |
| 19 | scored False, score 0.5 | load | error |
| 20 | factors missing "recency" | load | error |
| 21 | a row citing NPPES, but NPPES not in the entry's sources | load | error |
| 22 | the sample | finding_keys() | 5 keys in order; each row_id() equals its validation_row_id |
| 23 | the sample | to JSON and back | equal to the original |
| 24 | the sample | try to change a row's gold_value | error (frozen) |
| 25 | the sample with a typed-in total_conflicts of 9 | load | ignored or refused; totals always come from the entries |

### Files

- New: common/validation_report.py
- New: common/tests/fixtures/sample_report.json
- Changed: common/tests/test_contracts.py (add tests 1-25)
- Hand-written by owner: none. The owner checks the rules and builds the
  sample fixture by hand; Claude Code writes the code.

### Tasks

- [x] Build the sample fixture by hand and check it against the rules
- [x] Write failing tests for cases 1-25
- [x] Write common/validation_report.py until they pass
- [x] ruff, mypy, pytest pass
- [ ] Teammate reviews: this is the file their API reads
- [x] Tick "common/validation_report.py" in docs/plan.md, add a session log line
- [x] Phase 1 done: update "Current phase" in CLAUDE.md and "Now" in plan.md

## Notes for the next session

- 2026-11-25: Part 4 (evidence.py) code done, 264 tests pass; waiting on teammate
  review. raw_value is text (max 2,000 chars); an adapter that gets a list stores
  the source's text as given - confirm in review.
- Header-only fixture common/tests/fixtures/trust_source_systems.txt holds the 4
  trust-matrix source_system names; all 4 SourceIds match.
- Pydantic AwareDatetime refuses naive times; validators convert to UTC.
- 2026-11-25: Part 5 (search_plan.py) code done, 309 tests pass; waiting on teammate
  review. To confirm: task() raises KeyError when missing; UnplannedField's reason
  is not checked against the catalog (spec gives it only as a description).
- Gotcha: pydantic cannot serialize MappingProxyType, so SourceTask keeps
  trust_weights/search_params read-only and a field_serializer writes them as dicts.
  hide_input_in_errors keeps refused secret values out of error text.
- 2026-11-25: Part 6 (validation_report.py) code done, 360 tests pass; Phase 1 code
  complete, waiting on teammate review (their API reads this file). Fixture drafted by
  Claude with made-up values and approved by Anmol. Totals are computed fields; typed-in
  totals must match or the report is refused. conflicts = (field, representation) refs.
- To confirm in review: LocationRef renamed EvidenceLocationRef (evidence.LocationRef
  has another shape); rule 9 read as 'SET before every BY_LOCATION entry of its
  representation'; Confidence errors (rules 15-16) name the entry by path, not label.
- Gotcha: a field named `schema` shadows BaseModel.schema, so it is schema_version
  with alias 'schema' and serialize_by_alias.
- A reading guide for all six common/ files (API, rules, gotchas, open review
  questions, PR order) is in docs/common-notes.md.
