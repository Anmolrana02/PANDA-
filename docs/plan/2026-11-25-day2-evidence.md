# Day 2 session plan: 01 - contracts, Part 4 `common/evidence.py` (2026-11-25)

## Context

Every source adapter (CAQH, NPPES, website, Google) needs one fixed shape for
"what a source said", so the validator can compare any source with Gold and
every value can be traced to where and when it was found. Spec:
`docs/specs/01-contracts-02.md`, Part 4. Today `common/evidence.py` holds only
a docstring.

The repo is in this state:
- You split the spec into `01-contracts-01.md` (Parts 1-3) and
  `01-contracts-02.md` (Parts 4-6). The split is uncommitted. `-01` is the old
  `01-contracts.md` with only its title changed.
- PR #3 (`feat/01-finding-key`) is not merged yet, and that branch is checked out.

There are no hand-written files and no new dependencies.

## 0. Branch and save this plan

- `git switch -c feat/01-evidence` from `feat/01-finding-key`. The new PR is
  stacked on PR #3: its base is `feat/01-finding-key` until #3 merges, then
  `main`. This keeps the spec rename consistent with Part 3's ticks.
  `evidence.py` itself does not use `finding_key.py`.
- Copy this plan to `docs/plan/2026-11-25-day2-evidence.md`.
- Commit the spec split, the deleted `01-contracts.md` and the two new files on this branch.

## 1. Fixture for test 14 (you run this, then Claude reads the output)

Test 14 needs the trust matrix's source names, but the seed CSVs are gitignored
and absent in CI. As in Part 2, the fixture is names only, no data:

```
! uv run python -c "import pathlib; from data_plane.seed.load_seed import load_trust_matrix; names = sorted({r['source_system'] for r in load_trust_matrix()}); pathlib.Path('common/tests/fixtures/trust_source_systems.txt').write_text(chr(10).join(names) + chr(10), encoding='utf-8')"
```

If the column is not called `source_system`, the command fails. In that case
Claude stops and asks, and does not guess.

## 2. Tests first: `common/tests/test_contracts.py`

Add a `# --- Part 4: evidence ---` section:
- A `_assertion(**overrides)` helper builds the spec's NPPES degree example.
- A `_bundle(...)` helper wraps assertions in a bundle.
- Acceptance cases 1-20 are named `test_e01_...` to `test_e20_...`.
  - Errors expect `ValidationError`, with `match=` where the spec names a
    reason ("unknown field", "location field needs an office", "mixed sources").
  - 9: `datetime(2026, 11, 9, 22, 35, 7)` without tzinfo is refused.
  - 14: every `SourceId.trust_matrix_name` is in the new fixture.
  - 19: `EvidenceBundle.model_validate_json(b.model_dump_json()) == b`.

Extra tests for rules that no numbered case covers:
- Rule 3: NOT_FOUND with a `normalized_value` is refused. FOUND with
  `normalized_value=None` is valid.
- Rule 5: a raw_value of exactly 2,000 characters is valid.
- Rule 7: a `+05:30` retrieved_at is stored as the same instant in UTC.
  `source_last_update=None` is valid.
- Rule 8: a NOT_FOUND phone without a location_ref is valid. A NOT_FOUND degree
  with a location_ref is refused.
- Rule 10: an extra key such as `matches_directory` is refused (`extra="forbid"`).
- Rule 12: a bundle whose assertion differs in case_id, in npi or in
  data_group is refused (one parametrized test).
- Rule 13: a bundle made only of UNAVAILABLE assertions is valid.
- Rule 16: a single assertion with a location_ref round-trips through JSON.

Run `uv run pytest common` and show that the new tests fail before writing code.

## 3. Implementation: `common/evidence.py`

- StrEnums:
  - `SourceId`: `caqh`, `nppes`, `provider_website`, `google_search`. Its
    `trust_matrix_name` property reads a module-level read-only
    `MappingProxyType`: "CAQH", "NPPES", "Provider Website", "Google Searches".
  - `DataGroup`, `AssertionStatus` and `QualityLabel` use explicit upper-case
    values, as in Parts 1-2.
- `_Frozen` is a base `ConfigDict(frozen=True, extra="forbid")`. Not strict,
  so dates and enums still load from JSON. Pydantic v2 already refuses int to str.
- `LocationRef`:
  - `display_address: str` (min 1)
  - `location_name: str | None`
  - `practice_location_id: str | None`
- `EvidenceAssertion`:
  - Text fields:
    - `case_id`, `url_or_identifier` and `adapter_version` are `str`, min 1.
    - `npi` is `str` with `pattern=r"^\d{10}$"`.
    - `field_name` is `str`.
    - `raw_value` and `normalized_value` are `str | None`. raw_value has
      `max_length=2000` and is never stripped.
    - `status_detail` is `str | None`.
  - Enum fields: `data_group`, `source_id`, `status`, `quality_label`.
  - Date and office fields:
    - `retrieved_at` is an `AwareDatetime`, converted to UTC by a field validator.
    - `source_last_update` is a `date | None`.
    - `location_ref` is a `LocationRef | None`.
  - An after-validator checks:
    - the field via `get_field()`, turning `UnknownField` into "unknown field: 'fax'"
    - rule 3, value against status
    - rule 8, office against level
- `EvidenceBundle`:
  - `case_id`, `npi` (same pattern), `source_id` and `data_group`
  - `gold_version`, `trust_matrix_version` and `correlation_id`, each `str` min 1
  - `created_at`, an `AwareDatetime` in UTC
  - `assertions: tuple[EvidenceAssertion, ...]` with `min_length=1`. A tuple
    keeps order and stays immutable.
  - An after-validator enforces rule 12 and names the field that differs
    ("mixed sources" for source_id).
- `__all__`, type hints and docstrings. Nothing in the file scores, matches or routes.

Decision to confirm in review: `raw_value` is text. An adapter that gets a list
(e.g. languages) stores the source's text as given, up to 2,000 characters.

## 4. Checks

`uv run pytest`, `uv run ruff check .`, `uv run mypy .`, and `ruff format`
on the touched files must all pass.

## 5. Close-out

- `01-contracts-02.md` Part 4: tick the first three tasks and the plan.md one,
  leave "Teammate reviews" open, and fill in "Notes for the next session".
- `docs/plan.md`:
  - Point the Phase 1 spec reference at the two split files.
  - Split the open line so `common/evidence.py` is ticked and `search_plan.py`
    stays open.
  - Add one session-log line.
- Commit, push and open the PR only when you say so. `gh` is not installed,
  so I'll give you the compare link and a ready PR body.

## Files

- New:
  - `common/tests/fixtures/trust_source_systems.txt` (from your command)
  - `docs/plan/2026-11-25-day2-evidence.md`
  - `docs/specs/01-contracts-01.md` and `-02.md`, which you already created
- Changed: `common/evidence.py`, `common/tests/test_contracts.py`, `docs/plan.md`
- Deleted: `docs/specs/01-contracts.md` (replaced by `-01`)
- Reused: `get_field`, `FieldLevel` and `UnknownField` from `common/field_catalog.py`,
  and `_lines()`/`FIXTURES` in `test_contracts.py`

## Verification

- `uv run pytest common -v`: Parts 1-4 all pass, with the 20 acceptance cases
  plus the extras.
- `uv run mypy .` passes in strict mode, and `uv run ruff check .` is clean.
- `uv run python -c "from common.evidence import SourceId; print([s.trust_matrix_name for s in SourceId])"`
