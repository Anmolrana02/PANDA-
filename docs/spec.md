<!-- What the whole system must do. Replace with spec.md from the Project docs. -->
# PANDA - project spec

Status: draft v0.2 - 2026-11-15. Owners: <YOUR NAME>, <TEAMMATE>. Mentor: <NAME>.

This file says WHAT the system must do. It changes rarely. Day-to-day progress
lives in `plan.md`; the detail of one feature lives in `docs/specs/`.

## 1. Problem

A provider directory tells members which doctor exists, where they practise and
how to reach them. These facts go stale. PANDA checks each published fact
against approved sources and tells a human reviewer what looks wrong, with
evidence and a confidence score.

## 2. Goal and non-goals

Goal: for one provider NPI, produce a validation report covering all 29 audit
fields, and show it on a review screen where a human records a decision.

Non-goals (we will not build these):
- Updating the published directory.
- <e.g. user login with Azure identity>
- <e.g. reports and dashboards>

## 3. Users

- Reviewer: reads findings, accepts / modifies / flags for outreach / escalates.
- <Lead: queues audits - in or out of scope?>

## 4. The four records that must never be mixed

| Record | What it is | Who writes it |
|---|---|---|
| Directory Baseline | Published value at the pinned Gold version | nobody (read-only) |
| Evidence Assertion | What one source returned, with provenance | EVS adapters |
| Validation Finding | Outcome, recommendation, confidence for one field | agent graph |
| Audit Action | The reviewer's decision | portal API |

## 5. Audit fields (29)

Checked against the four CSVs on 2026-11-15.
- "Trust matrix" = `trust.csv` has at least one allowed source for the field.
- "Sample report" = the field appears in the reports in `validation.csv`.
- 13 fields have trust-matrix rows; 16 do not. The planner cannot plan evidence
  for a field with no trust-matrix row, so those 16 need a decision (section 13).

| Field | Level | Gold column(s) | Trust matrix | Sample report | Done |
|---|---|---|---|---|---|
| npi_type | provider | npi_type | yes | no | [ ] |
| provider_name | provider | first_name, middle_name, last_name | yes | yes | [ ] |
| provider_suffix | provider | suffix | yes | yes | [ ] |
| gender | provider | gender | yes | yes | [ ] |
| degree | provider | degree | yes | yes | [ ] |
| specialty | provider | primary_specialty, additional_specialties | yes | yes | [ ] |
| role | provider | role | yes | yes | [ ] |
| practice_locations | location SET | practice_location_id + address columns | yes | yes | [ ] |
| practice_address | by location | provider_address_line_1/2, provider_city, provider_state, provider_zip | yes | yes | [ ] |
| location_name | by location | location_name | yes | yes | [ ] |
| phone | by location | phone_number | yes | yes | [ ] |
| website | by location | web_address | yes | yes | [ ] |
| accepting_new_patients | by location | panel_status_accepting_new_patients | yes | yes | [ ] |
| network_participation | provider | unclear (pd_offer_cd? lob_source?) | no | yes | [ ] |
| board_certifications | provider | board_certifications | no | no | [ ] |
| medical_school | provider | provider_medical_school | no | no | [ ] |
| accreditation_status | provider | accreditation_status (empty in all 1000 rows) | no | no | [ ] |
| languages | provider | provider_languages | no | no | [ ] |
| license_status | provider | none found | no | no | [ ] |
| license_number | provider | none found (CAQH has `licence`) | no | no | [ ] |
| expiration_date | provider | none found | no | no | [ ] |
| practice_organization | by location (?) | org_name (?) | no | no | [ ] |
| office_hours | by location | office_hours | no | no | [ ] |
| weekend_hours | by location | weekend_hours | no | no | [ ] |
| patient_age_restrictions | by location | patient_age_restrictions | no | no | [ ] |
| office_languages | by location | office_languages | no | no | [ ] |
| accommodations | by location | office_services_ada | no | no | [ ] |
| interpreter_services | by location | office_services_interpreter | no | no | [ ] |
| telehealth | by location | remote_service_type | no | no | [ ] |

## 6. Agent graph

One case = one NPI. Nodes run in this order; each returns additive state and is
checkpointed.

| Node | Input | Output | LLM? |
|---|---|---|---|
| plan evidence | case, trust matrix | Search Plan | no |
| collect evidence | Search Plan | Evidence Bundles | only inside adapters |
| validate | Gold record, evidence | findings (CONFIRMED / DISCREPANCY / CANNOT_BE_VERIFIED / FATAL_FLAW) | no |
| score | findings | field and case confidence | no |
| route | scores | next action (vocabulary: see section 13) | no |
| write ledger | everything above | saved validation report | no |
| outreach | route | reviewer task or email; terminal state | no |

Agent case states: CREATED -> PLANNED -> RETRIEVING -> VALIDATING -> SCORING ->
ROUTING -> CLOSED or HITL_PENDING (CANCELLED on failure).

## 7. Scoring policy

Read the policy from `trust.csv`; never hard-code it.
- Matrix version in the file: `client-v2.0-caqh-nppes-web-google-2026-10-21`
  (59 rows, 55 active). Pin this version on every case.
- Source trust score by rank: rank 1 = 0.85, rank 2 = 0.60, rank 3 = 0.30.
- Five factors: authority, recency, quality, reliability, corroboration. The
  weights are stored per row in `acl_effective_weights`; there are five
  different weight sets, not one.
- Sensitivity tier per row: tier_1, tier_2, tier_3, tier_3_fatal.
- Allowed actions per row: `acl_allowed_actions`.
- Freshness limit per row: `freshness_days`. Human review flag per row:
  `human_review_required`.
- Case bands from the guide: >= 0.80 auto-confirm (needs minimum coverage of
  <X>); 0.65-0.79 human review; below 0.65 escalate. Confirm with mentor.
- Deductions: <list, e.g. duplicated source family, ambiguous location match>.

## 8. Sources (the four in the trust matrix)

| Source in trust.csv | Adapter | Runs where | Notes |
|---|---|---|---|
| CAQH | `caqh.py` | in-process | reads `caqh_.csv` |
| NPPES | `nppes.py` | EVS | public registry |
| Provider Website | `firecrawl_web.py` | EVS | LLM extraction, untrusted text |
| Google Searches | <`google_search.py`> | EVS | needs a search API - decide which |

## 9. Contracts (defined in `common/`)

Search Plan, Evidence Assertion, Evidence Bundle, Validation Report (schema-7),
FindingKey = (field_name, representation, location_key). Changing any of these
needs both owners. The sample reports use one representation only: "HPHC".

## 10. Data notes

- `gold_.csv`: 1000 providers, 46 columns. Location fields hold a JSON array in
  one cell, one element per location. Missing values are the text "null".
- `caqh_.csv`: 832 providers, all of them also in Gold; 168 Gold providers have
  no CAQH record.
- All four files wrap every line in an extra pair of quotes. A normal CSV
  reader sees one column; the loader must unwrap first.
- `validation.csv`: real schema-7 reports, 13 field entries each. It has stray
  line breaks inside values; only part of it parses. Use it as a format
  example and ask the mentor for a clean export.
- The files look like real internal data. Do not commit them until the mentor
  says they may be published.

## 11. Stores

| Store | Holds | Local | Cloud |
|---|---|---|---|
| Cosmos DB | agent case state, checkpoints | emulator | Azure |
| PostgreSQL | portal audits, cases, actions | container | Azure |
| Databricks | Gold, trust matrix, reports | <decide: see decisions/> | <decide> |
| Service Bus | evidence requests, ledger writes | emulator | Azure |
| Neo4j | provider - office - source graph | container | <decide> |
| MLflow | case traces, evaluation runs | container | <decide: Azure container or Databricks managed> |

## 12. Quality rules and definition of done

- Same inputs and policy version always give the same score.
- Re-running a finished case does not create duplicates.
- One failed source never fails the whole case.
- Every case run produces one MLflow trace tagged with case id, Gold version
  and trust-matrix version. Traces stay on our own server.
- [ ] One NPI runs end to end and all in-scope fields appear in the report.
- [ ] Every finding can be traced to its evidence and policy version.
- [ ] Evaluation: on <20> hand-checked providers, per-field agreement is
      logged in MLflow and reported in the README.
- [ ] A reviewer can record a decision on the screen and it is saved.
- [ ] Tests, ruff and mypy pass in CI.
- [ ] Runs on Azure from a clean deploy.

## 13. Open questions for the mentor

1. 16 of the 29 fields have no trust-matrix row and no sample report. Do we
   write our own source rules for them, or will he provide them?
2. The three license fields have no Gold column. What do we compare against?
3. Three action vocabularies exist: the guide (auto_confirm, needs_review,
   escalate...), trust.csv (AUTO_CLOSE, RECOMMEND_UPDATE, HITL...), and the
   sample reports (NO_CHANGE, ANALYST_REVIEW, KEEP_CREATE_LEAD...). Which one?
4. Can he give a clean export of `validation.csv`?
5. May the CSVs be committed to the repo?
6. Which graph store does he use?
7. Does the earlier Blueprint document still apply, or only the guide?