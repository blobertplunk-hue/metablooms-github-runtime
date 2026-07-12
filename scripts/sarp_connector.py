from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


VALID_VERDICTS = {
    "APPROVED",
    "APPROVED_WITH_CONDITIONS",
    "REJECTED",
    "BLOCKED_INSUFFICIENT_EVIDENCE",
    "CHANGES_REQUESTED",
}

FORBIDDEN_TRUE_FLAGS = (
    "implementation_authorized",
    "promotion_authorized",
    "github_write_authorized",
    "merge_authorized",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extract_first_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    raw = fenced.group(1) if fenced else text
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    return json.loads(raw[start : end + 1])


def validate_verdict_obj(obj: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if obj.get("schema") != "mb.github_connector.sarp_verdict.v1":
        errors.append({"code": "BAD_SCHEMA", "actual": obj.get("schema")})
    if obj.get("verdict") not in VALID_VERDICTS:
        errors.append({"code": "BAD_VERDICT", "actual": obj.get("verdict")})
    packet = obj.get("packet")
    if not isinstance(packet, dict):
        errors.append({"code": "PACKET_OBJECT_MISSING"})
    else:
        for key in ("manifest_path_or_url", "primary_archive_or_issue", "sha256_verified"):
            if key not in packet:
                errors.append({"code": "PACKET_FIELD_MISSING", "field": key})
    for key in ("bounded_question", "decision_summary", "next_allowed_action"):
        if not obj.get(key):
            errors.append({"code": "REQUIRED_TEXT_FIELD_EMPTY", "field": key})
    blocked = obj.get("blocked_actions")
    if not isinstance(blocked, list) or "promotion" not in blocked:
        errors.append({"code": "BLOCKED_ACTIONS_MISSING_PROMOTION"})
    for key in FORBIDDEN_TRUE_FLAGS:
        if obj.get(key) is not False:
            errors.append({"code": "AUTHORIZATION_FLAG_MUST_BE_FALSE", "field": key, "actual": obj.get(key)})
    return errors


def validate_verdict_file(path: Path, receipt: Path | None) -> int:
    text = path.read_text(encoding="utf-8")
    try:
        obj = extract_first_json_object(text)
        errors = validate_verdict_obj(obj)
    except Exception as exc:
        obj = None
        errors = [{"code": "VERDICT_PARSE_ERROR", "detail": f"{type(exc).__name__}:{exc}"}]
    result = {
        "schema": "mb.github_connector.sarp_verdict_validation.v1",
        "input": str(path),
        "input_sha256": sha256_file(path),
        "decision": "PASS" if not errors else "FAIL_BLOCKED",
        "errors": errors,
        "verdict": obj.get("verdict") if isinstance(obj, dict) else None,
    }
    if receipt:
        write_json(receipt, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


def validate_manifest(path: Path, receipt: Path | None) -> int:
    try:
        obj = load_json(path)
        errors: list[dict[str, Any]] = []
    except Exception as exc:
        obj = {}
        errors = [{"code": "MANIFEST_PARSE_ERROR", "detail": f"{type(exc).__name__}:{exc}"}]
    if obj.get("schema") != "mb.sarp_delivery.manifest.v1":
        errors.append({"code": "BAD_SCHEMA", "actual": obj.get("schema")})
    if not str(obj.get("primary_sarp_archive", "")).endswith(".tar.gz"):
        errors.append({"code": "PRIMARY_ARCHIVE_MISSING_OR_NOT_TARGZ"})
    files = obj.get("files")
    if not isinstance(files, list) or len(files) < 4:
        errors.append({"code": "TOO_FEW_SARP_FILES"})
    roles = {item.get("role") for item in files or [] if isinstance(item, dict)}
    for role in ("readme", "seed", "review_packet", "manifest"):
        if role not in roles:
            errors.append({"code": "REQUIRED_ROLE_MISSING", "role": role})
    result = {
        "schema": "mb.github_connector.sarp_manifest_validation.v1",
        "input": str(path),
        "input_sha256": sha256_file(path) if path.is_file() else None,
        "decision": "PASS" if not errors else "FAIL_BLOCKED",
        "errors": errors,
    }
    if receipt:
        write_json(receipt, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate GitHub connector SARP manifests and verdicts.")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate-verdict")
    v.add_argument("--file", required=True)
    v.add_argument("--receipt")
    m = sub.add_parser("validate-manifest")
    m.add_argument("--file", required=True)
    m.add_argument("--receipt")
    args = parser.parse_args(argv)
    if args.command == "validate-verdict":
        return validate_verdict_file(Path(args.file), Path(args.receipt) if args.receipt else None)
    if args.command == "validate-manifest":
        return validate_manifest(Path(args.file), Path(args.receipt) if args.receipt else None)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
