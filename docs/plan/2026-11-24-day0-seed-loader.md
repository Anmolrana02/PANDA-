# Day 0 session plan: 00 - seed loader (2026-11-24)

## Context

Phase 0 needs a seed loader before anything else can be built. Every later phase
(planner, CAQH adapter, validation) needs the Gold record, CAQH and the trust
matrix as clean Python data. The four seed CSVs wrap every line in an extra pair
of quotes, so a normal CSV reader sees one column. They also use the text `"null"`
for missing values and store location fields as JSON arrays in one cell.
Spec: `docs/specs/00-seed_loader.md`. This session delivers that spec as one small
PR. It also includes the minimal setup the loader needs: dev tools and CI.

Decisions made with the user today:
- **stdlib only** (`csv`, `json`, `pathlib`). Tables are `list[dict[str, Any]]`.
  No runtime dependency.
- Acceptance tests 1-3 use the real CSVs. They get a **`seed` pytest marker and
  skip with a clear reason when the CSV is absent**, for example in CI where the
  CSVs are gitignored.
- Scope: **loader plus minimal setup**: feature branch, dev deps, CI on pull requests.

## Steps

### 0. Housekeeping
- Create branch `feat/00-seed-loader` from `main`. Never commit to `main`.
- Save this plan to `docs/plan/2026-11-24-day0-seed-loader.md` (new folder
  `docs/plan/`).
- The untracked `docs/specs/00-seed_loader.md` goes in this branch.

### 1. Minimal setup (pyproject + CI)
- `uv add --dev pytest ruff mypy` (approved: dev tools only).
- `pyproject.toml`: register the `seed` marker next to `live`. Leave `addopts`
  alone, because `seed` tests skip by themselves when files are missing.
- `.github/workflows/ci.yml`: add the `pull_request: branches: [main]` trigger,
  as the comment in that file says to do once tests exist.

### 2. Learn the real file shape (read-only, headers only)
- Read **only the header line** of `gold_.csv`, `caqh_.csv` and `trust.csv` to
  get exact column names: NPI column, a location column such as `phone_number`,
  and the trust-matrix version and active columns. Never read data rows in bulk,
  never paste them into a prompt.
- If reading the header is blocked, ask the user for the column names.

**Done. Findings:**
- Files start with a UTF-8 BOM: open with `encoding="utf-8-sig"`. Lines end in CRLF.
- Each line is one CSV row stored as a single quoted cell with its inner quotes
  doubled. No `\"` escapes. Decoding it twice with `csv.reader` works.
- Data rows: Gold 1000, CAQH 832, trust 59 (matches the spec). Gold has 46 columns.
- Key columns: `npi` (Gold, CAQH), `phone_number` (Gold location list),
  `matrix_version` and `is_active` (trust).
- CAQH column names have typos/case quirks (`attenstation_date`, `licence`,
  `OFFICE_HOURS`). The loader keeps them as-is.
- Decisions added to the spec as rules 2, 3 and 3a, and acceptance cases 8-10:
  empty cell becomes None, list items are kept as text, JSON objects become dicts.

### 3. Tests first (`data_plane/tests/`)
- New `data_plane/tests/__init__.py`.
- New fixtures in `data_plane/tests/fixtures/`: tiny made-up `sample_gold.csv`
  (and a tiny trust sample if needed). They use the same wrapped-quote format as
  the real files, with fake data only. They include:
  - a `"null"` cell (test 4)
  - a provider with 5 locations in `phone_number` (test 5)
  - an NPI starting with `0` (test 6)
- New `data_plane/tests/test_load_seed.py`, one test per acceptance case:
  1. Gold: 1000 rows, 46 columns, no duplicate NPI (`seed`, skip if missing)
  2. CAQH: 832 rows, every NPI also in Gold (`seed`, skip if missing)
  3. Trust: 59 rows, 55 active, exactly one matrix version (`seed`, skip if missing)
  4. `"null"` becomes `None`
  5. 5-location provider: `phone_number` is a list of 5 items
  6. leading `0` in the NPI is kept, and the NPI is a `str`
  7. missing file raises `FileNotFoundError` whose message contains the file name
  - Plus a check for rule 5: the file's bytes and mtime are unchanged after loading.
- Run `uv run pytest data_plane` and **show that they fail** (the module has no
  functions yet).

### 4. Implement `data_plane/seed/load_seed.py`
Replace the current docstring, which wrongly says "into the stores". Loading into
stores is out of scope. Small typed functions:
- `SEED_DIR = Path(__file__).parent`
- `_unwrap_lines(path) -> list[str]`: open read-only (`encoding="utf-8"`,
  `newline=""`). Parse each physical line as a one-column CSV with `csv.reader`,
  which removes the outer quotes and un-doubles the inner `""`. Return the
  unwrapped line texts.
- `_parse_cell(value: str) -> Any`: `"null"` becomes `None`. Text starting with
  `[` that `json.loads` turns into a list becomes that list, with a `null` item
  becoming `None`. Anything else stays the string, so the NPI stays text.
- `load_csv(path: Path) -> list[dict[str, Any]]`: raise
  `FileNotFoundError(f"Seed file not found: {path}")` if the file is absent. Then
  run `csv.DictReader` over the unwrapped lines and apply `_parse_cell` to each cell.
- `load_gold(seed_dir=SEED_DIR)`, `load_caqh(...)`, `load_trust_matrix(...)`:
  thin wrappers around `gold_.csv`, `caqh_.csv` and `trust.csv`.
- No writes, no global state, no bare `except`. Catch only
  `json.JSONDecodeError` in `_parse_cell`.
- If step 2 shows the quoting differs from the assumption above, adjust
  `_unwrap_lines` only. The tests do not change.

**Done:** 14 tests pass, including cases 1-3 on the real CSVs. Every list and
object cell in the real data parses (Gold 22,000 list cells, CAQH 14,144,
trust 118 lists + 59 dicts). Also done: ruff-formatted the scaffold files
outside `common/` and added `.python-version` (3.12). The `.venv` was locked by
two Jupyter kernels; once they exited, `uv sync` rebuilt it on 3.12.

**Step 5 result (Python 3.12.16):** pytest 14 passed; ruff check clean; mypy
strict clean (86 files). `ruff format --check` still flags 7 files in `common/`,
left alone until both owners agree.

### 5. Verify
- `uv run pytest` (all pass. Locally the `seed` tests run against the real CSVs.)
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy .` (strict)
- Quick manual check: `uv run python -c "from data_plane.seed.load_seed import load_gold; r=load_gold(); print(len(r), len(r[0]))"`.
  Print counts only, no row contents.

### 6. Close out
- `docs/specs/00-seed_loader.md`: tick its tasks and fill "Notes for the next
  session" (column names found, quirks).
- `docs/plan.md`: tick "CSV loader that unwraps the extra quotes...". Update
  "Now". Add one session-log line dated 2026-11-24.
- Commit on the branch and open one small PR, **only after the user says go**.

## Files
- New: `data_plane/seed/load_seed.py` (replace the stub), `data_plane/tests/__init__.py`,
  `data_plane/tests/test_load_seed.py`, `data_plane/tests/fixtures/sample_*.csv`,
  `docs/plan/2026-11-24-day0-seed-loader.md`
- Edit: `pyproject.toml`, `uv.lock` (new), `.github/workflows/ci.yml`,
  `docs/plan.md`, `docs/specs/00-seed_loader.md`
- Not touched: `common/`, the CSVs, `validation.csv` (out of scope)
