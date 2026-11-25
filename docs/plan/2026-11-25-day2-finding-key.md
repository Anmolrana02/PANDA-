# Day 2 session plan: 01 - contracts, Part 3 `common/finding_key.py` (2026-11-25)

## Context

Reviewer decisions, field history and rationale all need one stable name for
"this finding". Spec: `docs/specs/01-contracts.md`, Part 3. It defines
`FindingKey = (field_name, representation, location_key)`, a frozen Pydantic v2
model that can be used as a dict key, checked against the field catalog.
Today `common/finding_key.py` holds only a docstring. Part 3 is still an
uncommitted edit to the spec on `main`.

No hand-written files here: the spec says Claude Code writes the code and the
owner checks it against the rules. No new dependencies (pydantic is already in).

## 0. Branch and save this plan

- `git switch -c feat/01-finding-key` from `main`. The uncommitted spec edit
  comes with it. (`feat/01-states` is already merged as PR #2.)
- Copy this plan to `docs/plan/2026-11-25-day2-finding-key.md`.

## 1. Tests first: `common/tests/test_contracts.py`

Add a `# --- Part 3: finding key ---` section with acceptance cases 1-16,
named `test_k01_...` to `test_k16_...` (Part 2 uses `c01`).
- Errors (4-9, 13, 16-style checks) expect `pydantic.ValidationError`, using
  `match=` for the reason the spec names ("location field", "provider field",
  "unknown field", empty address).
- 13: `key.location_key = "x"` raises `ValidationError` (frozen).
- 14: `FindingKey.from_str(key.to_str()) == key`.
- 15: `from_str("not a key")` raises `ValueError`.

Extra tests for rules that no numbered case covers:
- Rule 2: a PROVIDER field with an `"addr:..."` key is refused.
- Rule 4: an empty `location_key` is refused, and a non-string part
  (e.g. an int) is refused, not coerced.
- Rule 6: two equal keys have the same `hash()`. A key works as a dict key.
- Rule 8: a location key that contains `:`, `|` and `"` round-trips.
- Rule 9: `from_str` refuses a JSON list of 2 or 4 items, a list with a
  non-string item, a JSON object, and a valid list naming an unknown field.
- `is_provider_scope()` is True for `for_provider`, False for a location key.
- `is_reported_only()` is False for a Gold practice_location_id.
- The positional form from the spec's examples, `FindingKey("degree", "HPHC", "provider")`,
  equals `for_provider("degree", "HPHC")`.
- Extra keyword arguments (e.g. `address=`) are refused (rule 10: display text is not part of the key).

Run `uv run pytest common` and show that the new tests fail before writing code.

## 2. Implementation: `common/finding_key.py`

- `PROVIDER_SCOPE: Final = "provider"` and `REPORTED_ONLY_PREFIX: Final = "addr:"`.
- `class FindingKey(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid", strict=True)`.
  Its fields are `field_name: str`, `representation: str` and `location_key: str`,
  each `Field(min_length=1)`. Nothing is trimmed or lower-cased.
- `__init__(self, field_name, representation, location_key)` passes the three
  parts to `super().__init__` as keywords, so the spec's positional examples
  work. Keyword calls still work.
- `model_validator(mode="after")` uses `get_field()` from `common/field_catalog.py`:
  - It turns `UnknownField` into `ValueError("unknown field: 'fax'")` so pydantic
    reports it as a `ValidationError`.
  - PROVIDER: `location_key` must be `PROVIDER_SCOPE`, otherwise
    "degree is a provider field".
  - LOCATION: refuse `PROVIDER_SCOPE` ("phone is a location field") and a bare `"addr:"`
    ("empty address").
- Class methods `for_provider(field_name, representation)` and
  `for_location(field_name, representation, location_key)`.
- Instance methods:
  - `row_id()` returns `f"{field_name}:{location_key}"`.
  - `is_provider_scope()` checks `location_key == PROVIDER_SCOPE`.
  - `is_reported_only()` checks whether `location_key` starts with `"addr:"`.
- `to_str()` returns `json.dumps([f, r, l], ensure_ascii=False, separators=(",", ":"))`.
- `from_str(text)` uses `json.loads`. It requires a list of exactly 3 `str`,
  otherwise it raises `ValueError` naming the problem. Then it builds the key
  through the normal constructor, so every rule is checked again. It never guesses.
- `__all__`, full type hints, and a short docstring for each public name. "HPHC"
  is not hard-coded anywhere.

## 3. Checks

`uv run pytest`, `uv run ruff check .`, `uv run mypy .` and
`uv run ruff format` on the touched files must all pass. The format check on the
other `common/` stub files is still the known blocker.

## 4. Close-out

- Spec Part 3 tasks: tick the first three and the plan.md one. Leave "Teammate
  reviews" unticked. Add a line to "Notes for the next session".
- `docs/plan.md`: tick `common/finding_key.py` within the Phase 1 line (split the
  line so evidence and search_plan stay open), and add one session-log line.
- Commit and push to `feat/01-finding-key` and open a PR only when the user says so.

## Files

- New: `docs/plan/2026-11-25-day2-finding-key.md`
- Changed: `common/finding_key.py`, `common/tests/test_contracts.py`,
  `docs/specs/01-contracts.md`, `docs/plan.md`
- Reused: `get_field`, `FieldLevel` and `UnknownField` from `common/field_catalog.py`

## Verification

- `uv run pytest common -v`: Parts 1-3 all pass, with the 16 acceptance cases
  plus the extras.
- `uv run mypy .` passes in strict mode, and `uv run ruff check .` is clean.
- `uv run python -c "from common.finding_key import FindingKey as K; k = K.for_location('practice_locations', 'HPHC', 'addr:145 s st|boston ma 02111'); print(k.to_str(), k.row_id(), K.from_str(k.to_str()) == k)"`
