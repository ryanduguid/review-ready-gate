from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .errors import GateInputError, SchemaError
from .report import PACK_FILE_NAMES


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_review_sheet(pack_dir: Path) -> tuple[str, dict[str, str]]:
    json_path = pack_dir / "readiness-pack.json"
    summary_path = pack_dir / "readiness-summary.md"
    findings_path = pack_dir / "findings.csv"
    missing = [name for name in PACK_FILE_NAMES if not (pack_dir / name).is_file()]
    if missing:
        raise GateInputError(
            f"{pack_dir}: missing pack file(s): {', '.join(missing)}."
        )
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"{json_path}: not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise SchemaError(f"{json_path}: pack JSON must be an object.")
    required = {
        "acknowledgement",
        "engagement_type",
        "findings",
        "overall_status",
        "period_end",
        "preparer_initials",
        "review_boundary",
        "source_sha256",
        "thresholds",
    }
    actual = set(payload)
    if actual != required:
        raise SchemaError(f"{json_path}: unexpected or missing members {sorted(actual ^ required)}.")
    status = payload["overall_status"]
    if status not in {"READY", "NOT_READY", "BLOCKED"}:
        raise SchemaError(f"{json_path}: overall_status {status!r} is not a known status.")
    findings = payload["findings"]
    if not isinstance(findings, list):
        raise SchemaError(f"{json_path}: findings must be a list.")
    summary = summary_path.read_text(encoding="utf-8")
    status_line = f"**Overall status: {status}**"
    if status_line not in summary:
        raise SchemaError(
            f"{summary_path}: overall status line does not match readiness-pack.json."
        )
    if payload["review_boundary"] not in summary:
        raise SchemaError(f"{summary_path}: review-boundary statement is missing.")
    with findings_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(findings):
        raise SchemaError(
            f"{findings_path}: row count {len(rows)} does not match JSON findings {len(findings)}."
        )
    for index, (row, item) in enumerate(zip(rows, findings), start=2):
        if not isinstance(item, dict):
            raise SchemaError(f"{json_path}: finding {index - 1} is not an object.")
        if row.get("code") != item.get("code") or row.get("status") != item.get("status"):
            raise SchemaError(
                f"{findings_path}: row {index} does not match readiness-pack.json."
            )
    digests = {
        "readiness-pack.json": _sha256(json_path),
        "readiness-summary.md": _sha256(summary_path),
        "findings.csv": _sha256(findings_path),
    }
    lines = [
        summary.rstrip(),
        "",
        "## Artefact digests",
        "",
    ]
    for name, digest in digests.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.append("")
    return "\n".join(lines), digests
