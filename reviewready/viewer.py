"""Read-only display of an existing readiness pack.

Load the three generated artefacts, prove they agree with each other before
showing anything, and render the cover sheet. The viewer never writes, renames
or deletes a file, never opens a network connection, and never changes what
the engine computed. A tampered, partial or mismatched artefact set fails
closed with a named error instead of being displayed.

Every check here re-reads what ``report.write_review_pack`` emitted. The two
renderers are independent witnesses of one engine run: if their contents stop
agreeing, the pack is no longer trustworthy evidence and the reviewer must hear
that from this command rather than infer it from a plausible-looking sheet.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import GateInputError
from .report import PACK_FILE_NAMES, REVIEW_BOUNDARY

_JSON_NAME = "readiness-pack.json"
_SUMMARY_NAME = "readiness-summary.md"
_CSV_NAME = "findings.csv"

# The exact top-level members report._as_json emits, no more and no less. An
# added or removed member means the file was edited by something other than
# the writer that produced the other two artefacts.
_JSON_MEMBERS = frozenset(
    {
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
)

_ENGAGEMENTS = frozenset({"bas", "month_end", "year_end"})
_STATUSES = ("READY", "NOT_READY", "BLOCKED")
_FINDING_STATUSES = frozenset({"NOT_READY", "BLOCKED"})
_THRESHOLD_KEYS = ("tieout_tolerance",)

_CSV_FIELDS = (
    "code",
    "status",
    "slot",
    "repeat",
    "reason",
    "reviewer_action",
)

# Fields report._csv_safe guards with a leading apostrophe on the CSV side.
_CSV_GUARDED_FIELDS = frozenset({"slot", "reason", "reviewer_action"})

_ACK_MEMBERS = frozenset(
    {"reviewer_initials", "reviewed_on", "comment", "effect"}
)
_SOURCE_MEMBERS = frozenset({"filename", "sha256"})

_STATUS_LINE = re.compile(r"\*\*Overall status: (READY|NOT_READY|BLOCKED)\*\*")
_SOURCE_EVIDENCE_LINE = re.compile(
    r"- `([^`]+)` \(`([^`]+)`\): `([0-9a-f]{64})`"
)


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject a JSON object that states any member twice.

    A duplicated member is not valid evidence of anything: the two positions
    disagree about the pack, and standard json parsing would silently keep the
    last one, hiding the disagreement this command exists to surface.
    """
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise GateInputError(
                f"{_JSON_NAME}: member {key!r} appears more than once"
            )
        seen[key] = value
    return seen


def _load_artefact_bytes(pack_dir: Path) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for name in PACK_FILE_NAMES:
        path = pack_dir / name
        try:
            payloads[name] = path.read_bytes()
        except FileNotFoundError as exc:
            raise GateInputError(f"{name}: not found in {pack_dir}") from exc
        except IsADirectoryError as exc:
            raise GateInputError(f"{name}: expected a file, found a directory") from exc
    return payloads


def _parse_json(payload: bytes) -> dict[str, object]:
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except UnicodeDecodeError as exc:
        raise GateInputError(f"{_JSON_NAME}: not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise GateInputError(f"{_JSON_NAME}: not valid JSON ({exc.msg})") from exc
    if not isinstance(document, dict):
        raise GateInputError(f"{_JSON_NAME}: top level must be a JSON object")
    members = set(document)
    unknown = sorted(members - _JSON_MEMBERS)
    if unknown:
        raise GateInputError(
            f"{_JSON_NAME}: unknown top-level member(s): {', '.join(unknown)}"
        )
    missing = sorted(_JSON_MEMBERS - members)
    if missing:
        raise GateInputError(
            f"{_JSON_NAME}: missing top-level member(s): {', '.join(missing)}"
        )
    return document


def _parse_threshold(text: object, key: str) -> Decimal:
    if not isinstance(text, str):
        raise GateInputError(f"{_JSON_NAME}: thresholds.{key} must be a string")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise GateInputError(
            f"{_JSON_NAME}: thresholds.{key} is not a decimal: {text!r}"
        ) from exc
    if not value.is_finite() or value < 0:
        raise GateInputError(
            f"{_JSON_NAME}: thresholds.{key} must be finite and non-negative"
        )
    return value


def _verify_json_schema(document: dict[str, object]) -> None:
    status = document["overall_status"]
    if status not in _STATUSES:
        raise GateInputError(
            f"{_JSON_NAME}: overall_status must be one of "
            f"{', '.join(_STATUSES)}; got {status!r}"
        )
    engagement = document["engagement_type"]
    if engagement not in _ENGAGEMENTS:
        raise GateInputError(
            f"{_JSON_NAME}: engagement_type must be one of "
            f"{', '.join(sorted(_ENGAGEMENTS))}; got {engagement!r}"
        )
    for member in ("period_end", "preparer_initials", "review_boundary"):
        if not isinstance(document[member], str):
            raise GateInputError(f"{_JSON_NAME}: {member} must be a string")
    if document["review_boundary"] != REVIEW_BOUNDARY:
        raise GateInputError(
            f"{_JSON_NAME}: review_boundary does not match the written contract"
        )

    thresholds = document["thresholds"]
    if not isinstance(thresholds, dict) or set(thresholds) != set(_THRESHOLD_KEYS):
        raise GateInputError(
            f"{_JSON_NAME}: thresholds must hold exactly "
            f"{', '.join(_THRESHOLD_KEYS)}"
        )
    for key in _THRESHOLD_KEYS:
        _parse_threshold(thresholds[key], key)

    source_hashes = document["source_sha256"]
    if not isinstance(source_hashes, dict):
        raise GateInputError(f"{_JSON_NAME}: source_sha256 must be an object")
    for label, info in source_hashes.items():
        if not isinstance(info, dict) or set(info) != _SOURCE_MEMBERS:
            raise GateInputError(
                f"{_JSON_NAME}: source_sha256[{label!r}] must hold exactly "
                "filename and sha256"
            )
        filename = info["filename"]
        digest = info["sha256"]
        if not isinstance(filename, str) or not filename:
            raise GateInputError(
                f"{_JSON_NAME}: source_sha256[{label!r}].filename must be a non-empty string"
            )
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GateInputError(
                f"{_JSON_NAME}: source_sha256[{label!r}].sha256 is not a lowercase SHA-256 digest"
            )

    acknowledgement = document["acknowledgement"]
    if acknowledgement is not None:
        if not isinstance(acknowledgement, dict) or set(acknowledgement) != _ACK_MEMBERS:
            raise GateInputError(
                f"{_JSON_NAME}: acknowledgement must be null or hold exactly "
                f"{', '.join(sorted(_ACK_MEMBERS))}"
            )
        for key in _ACK_MEMBERS:
            if not isinstance(acknowledgement[key], str):
                raise GateInputError(
                    f"{_JSON_NAME}: acknowledgement.{key} must be a string"
                )

    findings = document["findings"]
    if not isinstance(findings, list):
        raise GateInputError(f"{_JSON_NAME}: findings must be a list")
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            raise GateInputError(f"{_JSON_NAME}: findings[{index}] must be an object")
        if item.get("status") not in _FINDING_STATUSES:
            raise GateInputError(
                f"{_JSON_NAME}: findings[{index}].status is not a finding status"
            )


def _summary_source_evidence(summary_text: str) -> dict[str, tuple[str, str]]:
    found = {
        slot: (filename, digest)
        for slot, filename, digest in _SOURCE_EVIDENCE_LINE.findall(summary_text)
    }
    if not found:
        raise GateInputError(f"{_SUMMARY_NAME}: no source-evidence digest lines found")
    return found


def _json_source_evidence(document: dict[str, object]) -> dict[str, tuple[str, str]]:
    source_hashes = document["source_sha256"]
    assert isinstance(source_hashes, dict)
    evidence: dict[str, tuple[str, str]] = {}
    for slot, info in source_hashes.items():
        assert isinstance(info, dict)
        filename = info["filename"]
        digest = info["sha256"]
        assert isinstance(filename, str)
        assert isinstance(digest, str)
        evidence[slot] = (filename, digest)
    return evidence


def _verify_cross_file_agreement(
    document: dict[str, object],
    summary_text: str,
    csv_rows: list[dict[str, str]],
) -> None:
    status = document["overall_status"]
    assert isinstance(status, str)

    status_lines = _STATUS_LINE.findall(summary_text)
    if len(status_lines) != 1:
        raise GateInputError(
            f"{_SUMMARY_NAME}: expected exactly one overall-status line, "
            f"found {len(status_lines)}"
        )
    if status_lines[0] != status:
        raise GateInputError(
            f"overall status disagrees: {_JSON_NAME} says {status}, "
            f"{_SUMMARY_NAME} says {status_lines[0]}"
        )

    if REVIEW_BOUNDARY not in summary_text:
        raise GateInputError(
            f"{_SUMMARY_NAME}: the review-boundary statement is missing or altered"
        )

    json_hashes = _json_source_evidence(document)
    if not json_hashes:
        if _SOURCE_EVIDENCE_LINE.search(summary_text):
            raise GateInputError(
                f"source evidence disagrees: {_SUMMARY_NAME} lists digests "
                f"but {_JSON_NAME} lists none"
            )
    else:
        summary_hashes = _summary_source_evidence(summary_text)
        if summary_hashes != json_hashes:
            raise GateInputError(
                f"source evidence disagrees: {_SUMMARY_NAME} and {_JSON_NAME} "
                f"list different source digests"
            )

    findings = document["findings"]
    assert isinstance(findings, list)
    if len(csv_rows) != len(findings):
        raise GateInputError(
            f"finding counts disagree: {_JSON_NAME} holds {len(findings)}, "
            f"{_CSV_NAME} holds {len(csv_rows)} data rows"
        )
    for index, (item, row) in enumerate(zip(findings, csv_rows)):
        for field in _CSV_FIELDS:
            expected = item.get(field)
            if not isinstance(expected, str):
                raise GateInputError(
                    f"{_JSON_NAME}: findings[{index}].{field} must be a string"
                )
            actual = row.get(field)
            if actual is None:
                raise GateInputError(f"{_CSV_NAME}: row {index + 1} has no {field} column value")
            if field in _CSV_GUARDED_FIELDS and expected.lstrip().startswith(
                ("=", "+", "-", "@")
            ):
                expected = "'" + expected
            if actual != expected:
                raise GateInputError(
                    f"{field} disagrees on finding {index + 1}: {_JSON_NAME} says "
                    f"{expected!r}, {_CSV_NAME} says {actual!r}"
                )


def _read_csv_rows(payload: bytes) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GateInputError(f"{_CSV_NAME}: not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != list(_CSV_FIELDS):
        raise GateInputError(
            f"{_CSV_NAME}: header row does not match the written contract"
        )
    return [
        {key: ("" if value is None else value) for key, value in row.items()}
        for row in reader
    ]


def verify_pack(pack_dir: Path) -> tuple[
    dict[str, object],
    str,
    list[dict[str, str]],
    dict[str, str],
]:
    """Verify one artefact set end to end and return its parsed contents.

    The returned mapping also carries the SHA-256 of each artefact's exact
    bytes under ``artefact_sha256``, so a displayed sheet can state what it
    actually read.
    """
    payloads = _load_artefact_bytes(pack_dir)
    document = _parse_json(payloads[_JSON_NAME])
    _verify_json_schema(document)
    try:
        summary_text = payloads[_SUMMARY_NAME].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateInputError(f"{_SUMMARY_NAME}: not valid UTF-8") from exc
    csv_rows = _read_csv_rows(payloads[_CSV_NAME])
    _verify_cross_file_agreement(document, summary_text, csv_rows)
    artefact_digests = {
        name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()
    }
    return document, summary_text, csv_rows, artefact_digests


def render_review_sheet(pack_dir: Path) -> tuple[str, dict[str, str]]:
    """Verify a pack and render it as a plain-text review sheet.

    Returns the sheet and the per-artefact digests it displays. Raises
    ``GateInputError`` instead of rendering whenever any artefact is
    missing, malformed or inconsistent with its siblings.
    """
    _document, summary_text, _csv_rows, artefact_digests = verify_pack(pack_dir)
    lines = [
        summary_text.rstrip(),
        "",
        "## Artefact digests",
        "",
    ]
    for name in PACK_FILE_NAMES:
        lines.append(f"- `{name}`: `{artefact_digests[name]}`")
    lines.append("")
    return "\n".join(lines), artefact_digests
