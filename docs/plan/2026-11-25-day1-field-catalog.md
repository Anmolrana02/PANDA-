# Day 1 session plan: 01 - contracts, Part 2 `common/field_catalog.py` (2026-11-25)

## Context

Every later phase (planner, validation, scoring, ledger, portal) needs to look
audit fields up in one place instead of typing field names itself. Spec:
`docs/specs/01-contracts.md`, Part 2. It defines the 29 audit fields, each
with its level, comparison mode, Gold columns, trust-matrix names and
coverage (13 COVERED, 16 PENDING_MENTOR). Today `common/field_catalog.py` holds
only a docstring.

Decisions made with the user today:
- **Add pydantic v2** (`uv add pydantic`), which the user approved.
  `FieldSpec` is a frozen `BaseModel`, as CLAUDE.md requires for contracts.
- **Header fixtures come from a command the user runs.** Reading the seed CSVs
  was blocked for Claude. The user runs two commands (below) that write header
  names only, no data, and Claude reviews the files.
- **Same branch** `feat/01-states`, added to the open PR.

## 0. Save this plan (done)

Copy this plan to `docs/plan/2026-11-25-day1-field-catalog.md`.

## 1. Dependency

Run `uv add pydantic`. This changes `pyproject.toml` and `uv.lock`. Then check
that `uv run mypy .` is still clean, without adding the pydantic mypy plugin
unless it turns out to be needed.

## 2. Fixtures (the user runs these, then Claude reads the two outputs)

Each command writes one name per line through Python, so it behaves the same
in bash and PowerShell and avoids the UTF-16 redirect in PowerShell 5.1.
They reuse `load_gold` and `load_trust_matrix` from `data_plane/seed/load_seed.py`,
which already handle the BOM and the wrapped quotes.

```
! uv run python -c "import pathlib; from data_plane.seed.load_seed import load_gold; pathlib.Path('common/tests/fixtures').mkdir(exist_ok=True); pathlib.Path('common/tests/fixtures/gold_columns.txt').write_text(chr(10).join(load_gold()[0]) + chr(10), encoding='utf-8')"
! uv run python -c "import pathlib; from data_plane.seed.load_seed import load_trust_matrix; names = sorted({r['canonical_field_name'] for r in load_trust_matrix()}); pathlib.Path('common/tests/fixtures/trust_field_names.txt').write_text(chr(10).join(names) + chr(10), encoding='utf-8')"
```

Claude then checks that `trust_field_names.txt` has 21 names, and that every
column and name in the spec table appears in the fixtures. If something in the
spec table is missing from them, Claude stops and reports it rather than
changing either the spec or the fixture.

## 3. Tests first: `common/tests/test_contracts.py`

Add a `# --- Part 2: field catalog ---` section with acceptance cases 1-15.
- 2: compare against the non-blank lines of `data_plane/seed/Audit Fields.txt`.
  That file is committed and is not a CSV.
- 10 and 11: compare against the two fixtures, read through a small helper
  `_fixture_lines(name)` that uses `Path(__file__).parent / "fixtures"`.
- 12: assigning `spec.level = ...` raises `pydantic.ValidationError`.
- 15: `IGNORED_TRUST_FIELDS` together with all catalog trust names equals the
  fixture set (21 names), and the two groups don't overlap.

Extra tests for rules that no numbered case covers:
- Rule 2: names are unique.
- Rule 5: every LOCATION field except practice_locations is BY_LOCATION, and
  every PROVIDER field is ONE_TO_ONE.
- Rule 9: only the four named fields have empty `gold_columns`.
- Building a FieldSpec whose coverage doesn't match its trust_fields fails
  validation (rule 8 enforced by the model).

Run `uv run pytest common` and show that the new tests fail before writing code.

## 4. Implementation: `common/field_catalog.py`

- StrEnums with explicit upper-case values:
  - `FieldLevel`: PROVIDER, LOCATION
  - `ComparisonMode`: ONE_TO_ONE, SET, BY_LOCATION
  - `Coverage`: COVERED, PENDING_MENTOR
- `class FieldSpec(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`
  and these fields:
  - `name: str`
  - `level: FieldLevel`
  - `mode: ComparisonMode`
  - `gold_columns: tuple[str, ...]`
  - `trust_fields: tuple[str, ...]`
  - `coverage: Coverage`

  A `model_validator(mode="after")` enforces rule 8: coverage is COVERED if and
  only if `trust_fields` is not empty.
- `_FIELDS: tuple[FieldSpec, ...]` holds the 29 entries, typed out from the
  spec table in Audit Fields.txt order. `_BY_NAME` is a `MappingProxyType`
  built from it. A duplicate name raises `ValueError` when the module is
  imported (rule 2).
- `IGNORED_TRUST_FIELDS: frozenset[str] = frozenset({"npi", "hospital_admitting_privileges"})`
- `class UnknownField(LookupError)`: its message names the field, e.g.
  `Unknown audit field: 'fax'`.
- Helpers, each returning a tuple in catalog order: `get_field(name)`,
  `all_fields()`, `provider_fields()`, `location_fields()`, `covered_fields()`.
- `__all__` lists the public names. Full type hints. No other file defines field names.

## 5. Checks

`uv run pytest`, `uv run ruff check .`, `uv run mypy .` and
`ruff format` on the touched files must all pass. The format check on the 5
other `common/` files is still the known blocker.

## 6. Close-out

- Spec Part 2 tasks: tick the first three and the plan.md one. Leave
  "Teammate reviews" unticked. Set Part 2's status to done once reviewed.
  Update "Notes for the next session", which currently says the next part is
  validation_report.
- `docs/plan.md`: tick `common/field_catalog.py` and add one session-log line.
- Commit and push to `feat/01-states` only when the user says so. This includes
  the pending spec edits from Part 1.

## Files

- New: `common/tests/fixtures/gold_columns.txt`, `common/tests/fixtures/trust_field_names.txt`
  (written by the user's commands), `docs/plan/2026-11-25-day1-field-catalog.md`
- Changed: `common/field_catalog.py`, `common/tests/test_contracts.py`,
  `pyproject.toml`, `uv.lock`, `docs/specs/01-contracts.md`, `docs/plan.md`

## Verification

- `uv run pytest common -v`: Part 1 and Part 2 tests all pass, including the
  real-header checks in cases 10, 11 and 15.
- `uv run mypy .` passes in strict mode, and `uv run ruff check .` is clean.
- `uv run python -c "from common.field_catalog import get_field; print(get_field('phone'))"`
  prints the FieldSpec from the spec's example.
