"""Read the seed CSVs (Gold, CAQH, trust matrix) into plain Python rows.

Spec: docs/specs/00-seed_loader.md. Read-only: this module never writes a file
and never loads anything into a store.

File format (all seed CSVs):
- a UTF-8 BOM at the start, CRLF line endings;
- every line is one normal CSV row stored as a single quoted cell, with its
  inner quotes doubled, so it has to be decoded twice;
- missing values are the text "null" or an empty cell;
- location fields hold a JSON list in one cell, one item per location;
- some trust-matrix cells hold a JSON object.
"""

import csv
import json
import re
from pathlib import Path
from typing import Any

SEED_DIR = Path(__file__).parent

GOLD_FILE = "gold_.csv"
CAQH_FILE = "caqh_.csv"
TRUST_FILE = "trust.csv"

Row = dict[str, Any]

# A bare number between list delimiters, e.g. the 04101 in [04101,04102].
_BARE_NUMBER = re.compile(r"(?<=[\[,])\s*(-?[0-9][0-9.eE+-]*)\s*(?=[,\]])")


def load_gold(seed_dir: Path = SEED_DIR) -> list[Row]:
    """Load the published (Gold) directory record: one row per provider."""
    return load_csv(seed_dir / GOLD_FILE)


def load_caqh(seed_dir: Path = SEED_DIR) -> list[Row]:
    """Load the CAQH extract: one row per provider that has a CAQH record."""
    return load_csv(seed_dir / CAQH_FILE)


def load_trust_matrix(seed_dir: Path = SEED_DIR) -> list[Row]:
    """Load the trust matrix: one row per (field, source) rule."""
    return load_csv(seed_dir / TRUST_FILE)


def load_csv(path: Path) -> list[Row]:
    """Load one wrapped seed CSV into rows keyed by the real column names."""
    if not path.is_file():
        raise FileNotFoundError(f"Seed file not found: {path}")
    reader = csv.reader(_unwrap_lines(path))
    header = next(reader, None)
    if header is None:
        raise ValueError(f"{path.name}: file is empty, expected a header line")
    rows: list[Row] = []
    for line_no, cells in enumerate(reader, start=2):
        if len(cells) != len(header):
            raise ValueError(
                f"{path.name} line {line_no}: expected {len(header)} columns, got {len(cells)}"
            )
        rows.append({name: _parse_cell(cell) for name, cell in zip(header, cells, strict=True)})
    return rows


def _unwrap_lines(path: Path) -> list[str]:
    """Remove the outer quotes around every line and return the inner CSV lines."""
    lines: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_no, outer in enumerate(csv.reader(handle), start=1):
            if not outer:
                continue
            if len(outer) != 1:
                raise ValueError(
                    f"{path.name} line {line_no}: expected one wrapped cell, got {len(outer)}"
                )
            lines.append(outer[0])
    return lines


def _parse_cell(value: str) -> Any:
    """Turn one raw cell into None, a list, a dict, or the original text."""
    if value in ("", "null"):
        return None
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return _parse_list(stripped, original=value)
    if stripped.startswith("{") and stripped.endswith("}"):
        return _parse_object(stripped, original=value)
    return value


def _parse_list(text: str, original: str) -> Any:
    """Parse a JSON list, keeping every item as text exactly as written."""
    for candidate in (text, _BARE_NUMBER.sub(r'"\1"', text)):
        try:
            parsed = json.loads(candidate, parse_int=str, parse_float=str, parse_constant=str)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [_as_text(item) for item in parsed]
    return original


def _parse_object(text: str, original: str) -> Any:
    """Parse a JSON object with plain JSON types; leave the text if it is not one."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return original
    return parsed if isinstance(parsed, dict) else original


def _as_text(item: Any) -> Any:
    """Keep a list item as text: None stays None, booleans become "true"/"false"."""
    if item is None or isinstance(item, (str, dict)):
        return item
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, list):
        return [_as_text(inner) for inner in item]
    return str(item)
