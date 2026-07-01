from pathlib import Path
from dataclasses import replace

from app.etl.extractor import extract_master
from app.etl.validation import validate_master


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_extracts_single_industry_company_a() -> None:
    master = extract_master(DATA_DIR / "corporates_A_1.xlsm")

    assert master.rated_entity_name == "Company A"
    assert master.sector == "Personal & Household Goods"
    assert master.currency == "EUR"
    assert master.country == "Federal Republic of Germany"
    assert master.industry_risks == [
        {"name": "Consumer Products: Non-Discretionary", "score": "A", "weight": 1.0}
    ]


def test_extracts_weight_change_for_company_b() -> None:
    before = extract_master(DATA_DIR / "corporates_B_1.xlsm")
    after = extract_master(DATA_DIR / "corporates_B_2.xlsm")

    assert [risk["weight"] for risk in before.industry_risks] == [0.15, 0.85]
    assert [risk["weight"] for risk in after.industry_risks] == [0.25, 0.75]


def test_validation_accepts_sample_files() -> None:
    for path in DATA_DIR.glob("*.xlsm"):
        report = validate_master(extract_master(path))
        assert not report.has_errors
        assert report.completeness_rate == 1.0


def test_validation_issues_include_rule_ids() -> None:
    master = replace(extract_master(DATA_DIR / "corporates_A_1.xlsm"), currency="Euro")
    report = validate_master(master)

    assert report.has_errors
    assert report.as_dict()["issues"][0]["rule_id"] == "currency_iso3_format"
