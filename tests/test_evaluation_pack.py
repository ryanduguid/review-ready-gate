from __future__ import annotations

import json
from pathlib import Path

from reviewready.engine import review_pack

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "evaluation" / "manager_review_gate"
EXPECTED = PACK / "expected_results.json"


def test_manager_review_evaluation_reproduces_the_declared_results() -> None:
    contract = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert contract["schema_version"] == 1
    assert contract["product_release"] == "0.1.1"
    assert contract["fixture_version"] == "1"
    for scenario in contract["scenarios"]:
        result = review_pack(
            profile=scenario["profile"],
            pack_dir=ROOT / scenario["fixture"],
        )
        assert result.status == scenario["expected_status"]
        assert sorted(item.code for item in result.findings) == sorted(
            scenario["expected_findings"]
        )


def test_manager_review_evaluation_keeps_the_human_decision_visible() -> None:
    contract = json.loads(EXPECTED.read_text(encoding="utf-8"))
    readme = (PACK / "README.md").read_text(encoding="utf-8")
    boundary = contract["human_decision"]
    assert boundary in readme
    assert "fabricated" in readme.casefold()
    assert "client workpaper" in readme.casefold()
    assert "case study" not in readme.casefold()


def test_manager_review_evaluation_names_sources_and_review_date() -> None:
    contract = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert contract["source_reviewed"] == "2026-08-26"
    assert {source["publisher"] for source in contract["sources"]} == {
        "Australian Taxation Office"
    }
    assert all(
        source["url"].startswith("https://www.ato.gov.au/")
        for source in contract["sources"]
    )
