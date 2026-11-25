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

## Notes for the next session

- 2026-11-25: Part 4 (evidence.py) code done, 264 tests pass; waiting on teammate
  review. raw_value is text (max 2,000 chars); an adapter that gets a list stores
  the source's text as given - confirm in review.
- Header-only fixture common/tests/fixtures/trust_source_systems.txt holds the 4
  trust-matrix source_system names; all 4 SourceIds match.
- Pydantic AwareDatetime refuses naive times; validators convert to UTC.