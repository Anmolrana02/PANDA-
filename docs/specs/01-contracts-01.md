<!-- Feature spec for the shared contracts in common/. Fill in from feature-spec-template.md. -->
# Feature spec: 01 - contracts -01

Owner: Anmol Rana + Harsh Giri (common/ is shared). Phase in plan.md: 1.
Status: in progress. Built one file at a time; each section below is one file.

## Goal

Give the agent graph, the case opener and the portal one shared, tested
definition of every status a case, dispatch job or batch can have, and of
which moves between statuses are allowed.

---

## Part 1 - common/states.py

Status: done (2026-11-25, branch feat/01-states).

### Inputs and outputs

- Input: a current status and a proposed next status.
- Output: True/False for "is this move allowed", or an InvalidTransition error.
- Statuses are Python StrEnums, so they save to JSON, Cosmos and Postgres
  as plain text, e.g. AgentCaseState.SCORING is stored as "SCORING".

### Statuses and allowed moves

Agent case (one NPI investigation):

    CREATED -> PLANNED -> RETRIEVING -> VALIDATING -> SCORING -> ROUTING
    ROUTING -> CLOSED          (safe to auto-confirm)
    ROUTING -> HITL_PENDING    (a human must review)
    any non-final status -> CANCELLED   (unrecoverable error)
    Final: CLOSED, HITL_PENDING, CANCELLED

Dispatch job (handing the case to the graph):

    PENDING -> DISPATCHING
    DISPATCHING -> DONE        (agent finished or already finished)
    DISPATCHING -> PENDING     (busy or temporary failure: retry later)
    DISPATCHING -> EXHAUSTED   (out of retries)
    Final: DONE, EXHAUSTED

Portal batch (confirmed by both owners 2026-11-25):

    OPEN -> ASSIGNED -> IN_PROGRESS -> REVIEWER_DECIDED
    REVIEWER_DECIDED -> CLOSED          (nothing escalated)
    REVIEWER_DECIDED -> EXPERT_REVIEW   (some findings escalated)
    EXPERT_REVIEW -> CLOSED
    Final: CLOSED

### Rules

1. Only the moves listed above are allowed. Everything else is refused.
2. Moving to the same status is refused (SCORING -> SCORING).
3. Nothing moves out of a final status.
4. CANCELLED is reachable from every non-final agent status, and from no
   final status.
5. The three state machines are separate: an agent status can never be
   checked against dispatch rules, and vice versa.
6. The allowed moves live in one table per machine, in this file only.
   No other file defines its own list.
7. The error message names both statuses, e.g.
   "Cannot move agent case from CREATED to SCORING".

### Out of scope

- Validation outcomes and comparison modes (Part 2, validation_report.py)
- Routing actions (waiting on mentor question 3)
- TERMINATED (in the guide, not in our spec.md; add only if needed)
- Export states and reassignment (portal cut list)
- Saving states anywhere; this file only defines and checks them

### Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | agent CREATED | move to PLANNED | allowed |
| 2 | agent CREATED | move to SCORING | refused (skips steps) |
| 3 | agent ROUTING | move to CLOSED, or to HITL_PENDING | both allowed |
| 4 | agent VALIDATING | move to CANCELLED | allowed |
| 5 | agent CLOSED | move to any status | refused (final) |
| 6 | agent CANCELLED | move to CANCELLED | refused |
| 7 | agent SCORING | move to SCORING | refused (same status) |
| 8 | agent SCORING | move to PLANNED | refused (no going back) |
| 9 | each agent status | ask is_final | true only for CLOSED, HITL_PENDING, CANCELLED |
| 10 | dispatch DISPATCHING | move to PENDING | allowed (retry) |
| 11 | dispatch EXHAUSTED | move to PENDING | refused (final) |
| 12 | dispatch PENDING | move to DONE | refused (must dispatch first) |
| 13 | portal REVIEWER_DECIDED | move to EXPERT_REVIEW, or to CLOSED | both allowed |
| 14 | portal IN_PROGRESS | move to CLOSED | refused (must finish review first) |
| 15 | agent CREATED -> SCORING | call require_transition | InvalidTransition naming both statuses |
| 16 | AgentCaseState.SCORING | convert to JSON | the text "SCORING" |
| 17 | every agent status | look up its allowed moves | every status has an entry in the table |

### Files

- New: common/states.py
- New: common/tests/test_contracts.py (states tests first; later parts add to it)
- Hand-written by owner: none. The owner writes and checks the move tables
  above; Claude Code turns them into code.

### Tasks

- [x] Teammate confirms the portal batch statuses
- [x] Write failing tests for cases 1-17
- [x] Write common/states.py until they pass
- [x] ruff, mypy, pytest pass
- [x] Tick "common/states.py" in docs/plan.md, add a session log line

---

## Part 2 - common/field_catalog.py

### What it is

One fixed list of the 29 audit fields. For each field it says whether it
belongs to the provider or to one location, how it is compared, which Gold
columns hold it, and which trust-matrix names give it sources. Every other
file looks fields up here instead of typing field names itself.

### Inputs and outputs

- Input: a field name, e.g. "phone".
- Output: a frozen FieldSpec:
  name="phone", level=LOCATION, mode=BY_LOCATION,
  gold_columns=("phone_number",), trust_fields=("phone_number",),
  coverage=COVERED
- Helpers: get_field(name), all_fields(), provider_fields(),
  location_fields(), covered_fields().

### Vocabulary (StrEnums defined in this file)

- FieldLevel: PROVIDER, LOCATION
- ComparisonMode: ONE_TO_ONE, SET, BY_LOCATION
  (validation_report.py imports it from here in Part 6)
- Coverage: COVERED (has trust-matrix rows), PENDING_MENTOR (no rows yet)

### The 29 fields

Order follows Audit Fields.txt.

| # | Field | Level | Mode | Gold column(s) | Trust-matrix name(s) | Coverage |
|---|---|---|---|---|---|---|
| 1 | npi_type | PROVIDER | ONE_TO_ONE | npi_type | npi_type | COVERED |
| 2 | provider_name | PROVIDER | ONE_TO_ONE | first_name, middle_name, last_name | first_name, middle_name, last_name | COVERED |
| 3 | provider_suffix | PROVIDER | ONE_TO_ONE | suffix | suffix | COVERED |
| 4 | gender | PROVIDER | ONE_TO_ONE | gender | gender | COVERED |
| 5 | degree | PROVIDER | ONE_TO_ONE | degree | degree | COVERED |
| 6 | board_certifications | PROVIDER | ONE_TO_ONE | board_certifications | - | PENDING_MENTOR |
| 7 | medical_school | PROVIDER | ONE_TO_ONE | provider_medical_school | - | PENDING_MENTOR |
| 8 | accreditation_status | PROVIDER | ONE_TO_ONE | accreditation_status | - | PENDING_MENTOR |
| 9 | specialty | PROVIDER | ONE_TO_ONE | primary_specialty, additional_specialties | primary_speciality, additional_specialities | COVERED |
| 10 | role | PROVIDER | ONE_TO_ONE | role | role | COVERED |
| 11 | practice_address | LOCATION | BY_LOCATION | provider_address_line_1, provider_address_line_2, provider_city, provider_state, provider_zip | the same five names | COVERED |
| 12 | practice_locations | LOCATION | SET | practice_location_id, provider_address_line_1, provider_address_line_2, provider_city, provider_state, provider_zip | provider_address_line_1, provider_address_line_2, provider_city, provider_state, provider_zip | COVERED |
| 13 | location_name | LOCATION | BY_LOCATION | location_name | location_name | COVERED |
| 14 | phone | LOCATION | BY_LOCATION | phone_number | phone_number | COVERED |
| 15 | website | LOCATION | BY_LOCATION | web_address | web_address | COVERED |
| 16 | office_hours | LOCATION | BY_LOCATION | office_hours | - | PENDING_MENTOR |
| 17 | weekend_hours | LOCATION | BY_LOCATION | weekend_hours | - | PENDING_MENTOR |
| 18 | accepting_new_patients | LOCATION | BY_LOCATION | panel_status_accepting_new_patients | panel_status_accepting_new_patients | COVERED |
| 19 | patient_age_restrictions | LOCATION | BY_LOCATION | patient_age_restrictions | - | PENDING_MENTOR |
| 20 | languages | PROVIDER | ONE_TO_ONE | provider_languages | - | PENDING_MENTOR |
| 21 | office_languages | LOCATION | BY_LOCATION | office_languages | - | PENDING_MENTOR |
| 22 | accommodations | LOCATION | BY_LOCATION | office_services_ada | - | PENDING_MENTOR |
| 23 | interpreter_services | LOCATION | BY_LOCATION | office_services_interpreter | - | PENDING_MENTOR |
| 24 | telehealth | LOCATION | BY_LOCATION | remote_service_type | - | PENDING_MENTOR |
| 25 | network_participation | PROVIDER | ONE_TO_ONE | (none yet - pd_offer_cd or lob_source?) | - | PENDING_MENTOR |
| 26 | license_status | PROVIDER | ONE_TO_ONE | (none) | - | PENDING_MENTOR |
| 27 | license_number | PROVIDER | ONE_TO_ONE | (none) | - | PENDING_MENTOR |
| 28 | expiration_date | PROVIDER | ONE_TO_ONE | (none) | - | PENDING_MENTOR |
| 29 | practice_organization | LOCATION | BY_LOCATION | org_name | - | PENDING_MENTOR |

Totals: 29 fields, 13 COVERED, 16 PENDING_MENTOR.

### Rules

1. The catalog has exactly 29 fields, with the same names and order as
   Audit Fields.txt.
2. Field names are unique.
3. Every FieldSpec is frozen: nothing can change it while the program runs.
4. Only practice_locations uses SET.
5. Every LOCATION field except practice_locations uses BY_LOCATION.
   Every PROVIDER field uses ONE_TO_ONE.
6. Every Gold column named here is a real column in gold_.csv.
7. Every trust-matrix name named here is a real canonical_field_name in
   trust.csv. (Note the spelling: trust says "speciality".)
8. A field is COVERED if and only if it has at least one trust-matrix name.
9. Only network_participation, license_status, license_number and
   expiration_date may have no Gold column.
10. get_field("unknown") raises UnknownField naming the field.
11. Trust-matrix names that belong to no audit field (npi,
    hospital_admitting_privileges) are left out on purpose; list them in a
    constant IGNORED_TRUST_FIELDS so this is visible, not forgotten.
12. Tests check rules 6 and 7 against fixed lists of column names copied
    into a test fixture (headers only, no data), not against the real CSVs.

### Out of scope

- Normalizers and comparators per field (Phase 4)
- Turning Gold list cells into per-location values (the loader and the
  validator do that)
- Whether a single-location provider uses ONE_TO_ONE instead of BY_LOCATION
  (decided in Part 6)
- Choosing sources for the 16 PENDING_MENTOR fields

### Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | the catalog | count all_fields() | 29 |
| 2 | the catalog and the Audit Fields.txt list | compare names in order | identical |
| 3 | the catalog | count covered_fields() | 13 |
| 4 | the catalog | list fields with mode SET | only practice_locations |
| 5 | get_field("phone") | read it | LOCATION, BY_LOCATION, gold ("phone_number",), COVERED |
| 6 | get_field("specialty") | read trust_fields | primary_speciality, additional_specialities |
| 7 | get_field("office_hours") | read it | trust_fields empty, PENDING_MENTOR |
| 8 | get_field("license_number") | read gold_columns | empty |
| 9 | get_field("fax") | call it | UnknownField naming "fax" |
| 10 | the Gold header fixture | check every gold column in the catalog | all found |
| 11 | the trust-matrix name fixture | check every trust name in the catalog | all found |
| 12 | any FieldSpec | try to change its level | error (frozen) |
| 13 | provider_fields() and location_fields() | combine them | all 29, no overlap |
| 14 | every field with trust_fields | check coverage | COVERED; every field without them is PENDING_MENTOR |
| 15 | IGNORED_TRUST_FIELDS plus all catalog trust names | compare with the trust fixture | they cover all 21 trust names exactly |

### Files

- New: common/field_catalog.py
- New: common/tests/fixtures/gold_columns.txt and trust_field_names.txt
  (header names only)
- Changed: common/tests/test_contracts.py (add tests 1-15)
- Hand-written by owner: none. The owner checks the table above; Claude Code
  turns it into code.

### Tasks

- [x] Write failing tests for cases 1-15
- [x] Write common/field_catalog.py until they pass
- [x] ruff, mypy, pytest pass
- [ ] Teammate reviews (common/ is shared)
- [x] Tick "common/field_catalog.py" in docs/plan.md, add a session log line
<next>


---

## Part 3 - common/finding_key.py

### What it is

The unique name tag of one finding: which field, in which directory
representation, at which location (or for the provider as a whole).
Reviewer decisions, field history and rationale are all stored under it.

    FindingKey = (field_name, representation, location_key)

### Inputs and outputs

- Input: field name, representation, location key.
- Output: a frozen Pydantic v2 model that can be used as a dict key.
  Examples from the sample reports:
  - FindingKey("degree", "HPHC", "provider")
  - FindingKey("phone", "HPHC", "3038479374")
  - FindingKey("practice_locations", "HPHC", "addr:145 s st|boston ma 02111")
- Helpers:
  - FindingKey.for_provider(field_name, representation)
  - FindingKey.for_location(field_name, representation, location_key)
  - key.row_id() -> "phone:3038479374" (same format as validation_row_id)
  - key.is_provider_scope(), key.is_reported_only()
  - key.to_str() / FindingKey.from_str(text) for URLs and database columns

### Vocabulary

- PROVIDER_SCOPE = "provider": the location key of every provider-level field.
- A location key starting with "addr:" is a location found only in evidence
  (no Gold practice_location_id).

### Rules

1. field_name must be one of the 29 fields in field_catalog.py.
2. A PROVIDER field must use location key "provider".
3. A LOCATION field must not use "provider"; its key is either a Gold
   practice_location_id or "addr:" followed by at least one character.
4. representation and location_key must be non-empty and are kept exactly as
   given: no trimming, no changing case. Do not hard-code "HPHC".
5. A key is frozen: its parts cannot change after it is made.
6. Two keys are equal only if all three parts are equal, and equal keys
   have the same hash.
7. row_id() returns "<field_name>:<location_key>", matching the sample
   reports exactly.
8. to_str() and from_str() round-trip every key, including location keys
   that contain ":" or "|". (Store the string as a JSON list of the three
   parts, not by joining with a separator.)
9. from_str() on broken text raises an error; it never guesses.
10. Display text (addresses, office names) is never part of the key.

### Out of scope

- The display context of a location (address text, office name); that lives
  in the validation row (Part 6)
- How the "addr:" text is built from an address (validation phase)
- Review ordering of findings (portal)
- Storing keys in a database

### Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | for_provider("degree", "HPHC") | make it | location_key "provider", row_id "degree:provider" |
| 2 | for_location("phone", "HPHC", "3038479374") | make it | row_id "phone:3038479374" |
| 3 | for_location("practice_locations", "HPHC", "addr:145 s st\|boston ma 02111") | make it | is_reported_only() is True |
| 4 | for_provider("phone", "HPHC") | make it | error: phone is a location field |
| 5 | for_location("degree", "HPHC", "3038479374") | make it | error: degree is a provider field |
| 6 | for_location("phone", "HPHC", "provider") | make it | error |
| 7 | for_location("phone", "HPHC", "addr:") | make it | error: empty address |
| 8 | field_name "fax" | make it | error: unknown field |
| 9 | representation "" | make it | error |
| 10 | phone key at location 1 and at location 2 | compare | not equal |
| 11 | same phone key in "HPHC" and in "REP_B" | compare | not equal |
| 12 | two keys made from the same parts | put both in a set | set has 1 item |
| 13 | any key | try to change location_key | error (frozen) |
| 14 | the key from test 3 | to_str() then from_str() | equal to the original |
| 15 | text "not a key" | from_str() | error |
| 16 | representation " HPHC" with a space | make it | kept exactly, not equal to "HPHC" |

### Files

- New: common/finding_key.py
- Changed: common/tests/test_contracts.py (add tests 1-16)
- Hand-written by owner: none. The owner checks the rules above; Claude Code
  writes the code.

### Tasks

- [x] Write failing tests for cases 1-16
- [x] Write common/finding_key.py until they pass
- [x] ruff, mypy, pytest pass
- [ ] Teammate reviews (they store decisions under this key)
- [x] Tick "common/finding_key.py" in docs/plan.md, add a session log line

## Notes for the next session

- 2026-11-25: Part 1 (states.py) done: 3 StrEnum machines, one read-only move
  table each, 113 tests pass. Portal batch statuses confirmed by both owners.
- Gotcha: StrEnum members compare equal by text (AgentCaseState.CLOSED ==
  PortalBatchState.CLOSED), so states.py raises TypeError when machines are mixed.
  Later contracts that key on statuses should keep the enum type, not plain strings.
- CI's `ruff format --check` still fails on the 5 docstring-only files in common/
  until both owners OK formatting them.
- 2026-11-25: Part 2 (field_catalog.py) code done, 190 tests pass; waiting on
  teammate review before marking it done. Added pydantic (FieldSpec is a frozen
  BaseModel). Header-only fixtures in common/tests/fixtures/ (46 Gold columns,
  21 trust names) were generated from the seed CSVs with load_seed.py.
- Gold has look-alike columns the catalog does not use: provider_specialty,
  provider_additional_specialty, provider_role, provider_accepting_new_patients
  (the catalog uses primary_specialty, additional_specialties, role,
  panel_status_accepting_new_patients). Confirm with the mentor which are current.
- Next: Part 3 of spec 01 (evidence, search_plan, finding_key); its section needs
  writing first.
- 2026-11-25: Part 3 (finding_key.py) code done, 224 tests pass; waiting on teammate
  review. Gotcha: pydantic sends model_validate through an overridden __init__, so
  FindingKey.__init__ passes **extra on to pydantic to keep extra="forbid" working.
