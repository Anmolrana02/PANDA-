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
