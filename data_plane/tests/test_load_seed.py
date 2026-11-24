"""Acceptance tests for docs/specs/00-seed_loader.md (cases 1-10).

Cases 1-3 read the real seed CSVs. They are gitignored, so those tests skip when
the files are absent (for example in CI). Their assertions report counts only,
never row contents. Every other case uses the tiny made-up fixtures.
"""

from pathlib import Path

import pytest

from data_plane.seed.load_seed import (
    SEED_DIR,
    load_caqh,
    load_csv,
    load_gold,
    load_trust_matrix,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_GOLD = FIXTURES / "sample_gold.csv"
SAMPLE_TRUST = FIXTURES / "sample_trust.csv"


def _needs_seed(*names: str) -> pytest.MarkDecorator:
    missing = [n for n in names if not (SEED_DIR / n).is_file()]
    return pytest.mark.skipif(bool(missing), reason=f"seed CSV absent: {', '.join(missing)}")


def _row(rows: list[dict[str, object]], npi: str) -> dict[str, object]:
    matches = [r for r in rows if r["npi"] == npi]
    assert len(matches) == 1, f"expected one row for NPI ending {npi[-4:]}, got {len(matches)}"
    return matches[0]


# --- Cases 1-3: real seed CSVs -------------------------------------------------


@pytest.mark.seed
@_needs_seed("gold_.csv")
def test_1_gold_shape() -> None:
    rows = load_gold()
    assert len(rows) == 1000
    assert all(len(r) == 46 for r in rows), "every Gold row should have 46 columns"
    npis = [r["npi"] for r in rows]
    duplicates = len(npis) - len(set(npis))
    assert duplicates == 0, f"{duplicates} duplicate NPIs in Gold"


@pytest.mark.seed
@_needs_seed("gold_.csv", "caqh_.csv")
def test_2_caqh_npis_all_in_gold() -> None:
    caqh = load_caqh()
    assert len(caqh) == 832
    gold_npis = {r["npi"] for r in load_gold()}
    not_in_gold = sum(1 for r in caqh if r["npi"] not in gold_npis)
    assert not_in_gold == 0, f"{not_in_gold} CAQH NPIs are not in Gold"


@pytest.mark.seed
@_needs_seed("trust.csv")
def test_3_trust_matrix_shape() -> None:
    rows = load_trust_matrix()
    assert len(rows) == 59
    active = sum(1 for r in rows if str(r["is_active"]).lower() == "true")
    assert active == 55
    versions = {r["matrix_version"] for r in rows}
    assert len(versions) == 1, f"expected one matrix version, got {len(versions)}"


# --- Cases 4-10: made-up sample fixtures ---------------------------------------


def test_4_null_text_becomes_none() -> None:
    row = _row(load_csv(SAMPLE_GOLD), "1000000001")
    assert row["middle_name"] is None


def test_5_five_locations_give_five_phone_numbers() -> None:
    row = _row(load_csv(SAMPLE_GOLD), "1000000001")
    assert row["phone_number"] == [
        "5550000001",
        "5550000002",
        "5550000003",
        "5550000004",
        "5550000005",
    ]


def test_6_npi_leading_zero_is_kept_as_text() -> None:
    npis = [r["npi"] for r in load_csv(SAMPLE_GOLD)]
    assert "0123456789" in npis
    assert all(isinstance(n, str) for n in npis)


def test_7_missing_file_error_names_the_file(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_seed.csv"
    with pytest.raises(FileNotFoundError, match="no_such_seed.csv"):
        load_csv(missing)


def test_7_missing_seed_dir_file_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="gold_.csv"):
        load_gold(tmp_path)


def test_8_empty_cell_becomes_none() -> None:
    row = _row(load_csv(SAMPLE_GOLD), "0123456789")
    assert row["middle_name"] is None


def test_9_bare_number_list_items_stay_text() -> None:
    rows = load_csv(SAMPLE_GOLD)
    assert _row(rows, "1000000001")["provider_zip"] == [
        "04101",
        "04102",
        "04103",
        "04104",
        "04105",
    ]
    assert _row(rows, "0123456789")["provider_zip"] == ["02139"]


def test_rule_3_null_list_item_becomes_none() -> None:
    row = _row(load_csv(SAMPLE_GOLD), "0123456789")
    assert row["phone_number"] == ["5550000009", None]


def test_10_json_object_cell_becomes_dict() -> None:
    rows = load_csv(SAMPLE_TRUST)
    assert rows[0]["acl_effective_weights"] == {"source_trust": 0.5, "freshness": 0.25}
    assert rows[0]["acl_allowed_actions"] == ["AUTO_CLOSE", "HITL"]
    assert rows[1]["acl_allowed_actions"] == []


def test_header_has_no_bom_or_wrapping_quotes() -> None:
    rows = load_csv(SAMPLE_GOLD)
    assert list(rows[0]) == ["npi", "first_name", "middle_name", "phone_number", "provider_zip"]
    assert len(rows) == 2


def test_rule_5_loader_never_changes_the_file() -> None:
    before_bytes = SAMPLE_GOLD.read_bytes()
    before_mtime = SAMPLE_GOLD.stat().st_mtime_ns
    load_csv(SAMPLE_GOLD)
    assert SAMPLE_GOLD.read_bytes() == before_bytes
    assert SAMPLE_GOLD.stat().st_mtime_ns == before_mtime
