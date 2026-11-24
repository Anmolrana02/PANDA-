# Feature spec: 00 - seed loader

Owner: <Anmol , Harsh>. Phase in plan.md: 0. Status: done (2026-11-24).

## Goal

Read the four seed CSVs correctly, so the rest of the system can get any
provider's Gold record and the trust matrix as clean Python data.

## Inputs and outputs

- Input: data_plane/seed/gold_.csv, caqh_.csv, trust.csv
- Output: one table per file, with real column names and real missing values.
  Location columns come back as Python lists, one item per location.
  Example: phone_number '["2075632311","8442920111"]' becomes
  ["2075632311", "8442920111"].

## Rules

1. Remove the extra quote marks that wrap every line before reading.
2. The text "null" and an empty cell both become a real missing value (None).
3. Cells that hold a JSON list are turned into Python lists. Every item is kept
   as text exactly as written (bare numbers too, so "04101" stays "04101");
   a null item becomes None.
3a. Cells that hold a JSON object (e.g. trust.csv `acl_effective_weights`) are
   turned into Python dicts with plain JSON types.
4. NPI is read as text, not a number, so no leading digit is ever lost.
5. The loader only reads. It never changes or saves the CSV files.
6. A missing file gives a clear error that names the file.
7. Tests use a tiny made-up sample file, not the real CSVs.

## Out of scope

- validation.csv (it is broken; we wait for a clean copy from the mentor)
- Loading into Databricks, Postgres or any other database
- Checking whether the values are correct

## Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | gold_.csv | load Gold | 1000 rows, 46 columns, no duplicate NPI |
| 2 | caqh_.csv | load CAQH | 832 rows, every NPI is also in Gold |
| 3 | trust.csv | load trust matrix | 59 rows, 55 active, one matrix version |
| 4 | a cell with text "null" | load | value is None |
| 5 | a provider with 5 locations | load | phone_number is a list of 5 items |
| 6 | an NPI starting with 0 in the sample file | load | the 0 is kept |
| 7 | file not found | load | error message names the file |
| 8 | an empty cell in the sample file | load | value is None |
| 9 | a list cell with bare numbers, one with a leading 0 | load | items are strings, the 0 is kept |
| 10 | a trust sample row with a JSON object cell | load | value is a dict |

## Files

- New: data_plane/seed/load_seed.py
- New: data_plane/tests/test_load_seed.py and a small sample CSV fixture
- Hand-written by owner: none (this is helper code; Claude Code can write it)

## Tasks

- [x] Write failing tests for cases 1-10
- [x] Write load_seed.py until they pass
- [x] ruff, mypy, pytest pass (except `ruff format` on `common/`, see notes)
- [x] Tick the loader task in docs/plan.md, add a session log line

## Notes for the next session

- API: `load_gold()`, `load_caqh()`, `load_trust_matrix()` (optional `seed_dir`),
  and `load_csv(path)`. Rows are `dict[str, Any]` keyed by the real column names.
- File format: UTF-8 BOM, CRLF, each line one CSV row stored as a single quoted
  cell, so it is decoded twice. Open with `utf-8-sig`.
- Real data: every JSON-looking cell parses (Gold 22,000 list cells, CAQH
  14,144, trust 118 lists + 59 objects); none is left as text.
- CAQH column names keep the source's typos and capitals (`attenstation_date`,
  `licence`, `OFFICE_HOURS`, `primary_speciality`). Mapping them to Gold names
  belongs in the CAQH adapter (phase 3), not here.
- Trust `is_active` is the text "true"/"false"; `trust_score` and other numbers
  are text too. Converting types is the trust-matrix loader's job (phase 3).
- Tests 1-3 carry the `seed` marker and skip when the CSVs are absent (CI).
- Open: the 7 files in `common/` fail `ruff format --check`, which fails CI.
  Format them once both owners agree.