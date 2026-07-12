from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from metablooms_sandbox_factory.factory_common import sha256_file, write_json


def _name_is_safe(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or "\x00" in normalized:
        return False
    parts = [p for p in normalized.split("/") if p]
    return not any(p == ".." for p in parts)


def _list_with_python_tar(path: Path) -> tuple[str, list[str], list[str]]:
    errors: list[str] = []
    names: list[str] = []
    try:
        with tarfile.open(path, "r:*") as tf:
            for member in tf.getmembers():
                names.append(member.name)
                if not _name_is_safe(member.name):
                    errors.append(f"unsafe_tar_member:{member.name}")
                if member.issym() or member.islnk():
                    errors.append(f"link_member_not_allowed:{member.name}")
    except Exception as exc:
        errors.append(f"python_tar_validation_error:{type(exc).__name__}:{exc}")
    return "python_tarfile", names, errors


def _list_with_system_tar(path: Path) -> tuple[str, list[str], list[str]]:
    errors: list[str] = []
    names: list[str] = []
    try:
        cp = subprocess.run(
            ["tar", "-tf", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
    except Exception as exc:
        return "system_tar", names, [f"system_tar_error:{type(exc).__name__}:{exc}"]
    if cp.returncode != 0:
        errors.append(f"system_tar_exit:{cp.returncode}:{cp.stderr.strip()[:500]}")
    names = [line for line in cp.stdout.splitlines() if line.strip()]
    for name in names:
        if not _name_is_safe(name):
            errors.append(f"unsafe_tar_member:{name}")
    return "system_tar", names, errors


def inspect_archive_members(path: Path) -> tuple[str, list[str], list[str]]:
    validator, names, errors = _list_with_python_tar(path)
    if names or not path.name.endswith(".zst"):
        return validator, names, errors
    system_validator, system_names, system_errors = _list_with_system_tar(path)
    if system_names:
        return system_validator, system_names, system_errors
    return validator, names, [*errors, *system_errors]


def verify_archive(path: Path, expected_sha256: str | None = None, output_path: Path | None = None) -> dict[str, Any]:
    exists = path.is_file()
    actual = sha256_file(path) if exists else None
    safe = False
    errors: list[str] = []
    members = 0
    first_member = None
    validator = None
    if exists:
        validator, names, errors = inspect_archive_members(path)
        safe = not errors and bool(names)
        members = len(names)
        first_member = names[0] if names else None
    result = {
        "schema": "mb.sandbox_factory.artifact_verification.v1",
        "path": str(path),
        "validator": validator,
        "exists": exists,
        "sha256": actual,
        "expected_sha256": expected_sha256,
        "sha256_matches": bool(actual and expected_sha256 and actual.lower() == expected_sha256.lower()) if expected_sha256 else None,
        "safe_members": safe,
        "member_count": members,
        "first_member": first_member,
        "errors": errors,
        "verdict": "PASS" if exists and safe and not errors and (not expected_sha256 or actual.lower() == expected_sha256.lower()) else "BLOCKED",
    }
    if output_path:
        write_json(output_path, result)
    return result


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--archive", required=True)
    p.add_argument("--expected-sha256")
    p.add_argument("--output")
    args = p.parse_args()
    result = verify_archive(Path(args.archive), args.expected_sha256, Path(args.output) if args.output else None)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
