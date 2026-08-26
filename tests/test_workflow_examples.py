from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from tests.support import EXAMPLES, ROOT

WORKFLOW = EXAMPLES / "github-actions-readiness-check.yml"

EXPECTED_PINS = (
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
)


def test_copyable_workflow_discovery_is_not_vacuous() -> None:
    workflows = sorted({*EXAMPLES.rglob("*.yml"), *EXAMPLES.rglob("*.yaml")})
    assert workflows == [WORKFLOW]


def test_copyable_workflow_is_scheduled_and_fail_closed_on_blocked() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for pin in EXPECTED_PINS:
        assert pin in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "python -m pip install ." in text
    assert "--pack examples/bas-not-ready" in text
    assert 'if [ "$status" = "BLOCKED" ]' in text
    assert "NOT_READY" in text
    assert "READY still does not mean the file is approved" in text
    assert "fabricated or synthetic data" in text
    assert "Never commit a\n# client workpaper pack." in text


def test_releasing_runbook_is_this_repo_and_does_not_tag_yet() -> None:
    text = (ROOT / "RELEASING.md").read_text(encoding="utf-8")
    assert "repos/ryanduguid/review-ready-gate/immutable-releases" in text
    assert "Workflow filename | `release.yml`" in text
    assert "Environment name | `pypi`" in text
    assert "review_ready_gate-0.1.1-py3-none-any.whl" in text
    assert "intend to publish." in text
    assert "The first successful workflow creates the PyPI project." in text


def test_failed_release_tag_is_not_reused() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == "0.1.1"


def test_release_notes_heading_matches_release_policy_tag() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    heading = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8").splitlines()[0]
    assert heading == f"# v{metadata['project']['version']}"


def test_readme_development_uses_the_locked_uv_entrypoint() -> None:
    development = (ROOT / "README.md").read_text(encoding="utf-8").split("## Development", 1)[1]
    block = development.split("```bash", 1)[1].split("```", 1)[0]
    assert "uv run pytest" in block
    assert "uv lock --check" in block
    assert "python -m pytest" not in block


def test_citation_declares_the_first_release_identity() -> None:
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert 'title: "review-ready-gate"' in citation
    assert "version: 0.1.1" in citation
    assert 'family-names: "Duguid"' in citation
    assert 'given-names: "Ryan"' in citation
    assert "license: MIT" in citation
    assert 'repository-code: "https://github.com/ryanduguid/review-ready-gate"' in citation


def test_project_homepage_points_to_the_published_tool_page() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["urls"]["Homepage"] == (
        "https://ryanduguid.github.io/tools/review-ready-gate/"
    )


def test_discovery_record_matches_the_approved_remote_metadata() -> None:
    discovery = (ROOT / "docs" / "DISCOVERY.md").read_text(encoding="utf-8")
    assert discovery == (
        "# GitHub discovery metadata\n\n"
        "Description: Stop incomplete workpapers reaching manager review. "
        "Deterministic readiness gate for Australian public-practice packs. Not advice.\n\n"
        "Homepage: https://ryanduguid.github.io/tools/review-ready-gate/\n\n"
        "Topics:\n\n"
        "- accounting\n"
        "- accounting-controls\n"
        "- australia\n"
        "- bas\n"
        "- cli\n"
        "- month-end\n"
        "- public-practice\n"
        "- python\n"
        "- quality-control\n"
        "- review\n"
        "- review-workflow\n"
        "- workpapers\n"
        "- year-end\n"
    )
