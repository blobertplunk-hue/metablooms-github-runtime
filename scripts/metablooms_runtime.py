from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "metablooms_runtime_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def member_name_safe(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or "\x00" in normalized:
        return False
    parts = [part for part in normalized.split("/") if part]
    return not any(part == ".." for part in parts)


def locate_archive(manifest: dict[str, Any]) -> Path | None:
    archive = manifest["runtime_archive"]
    url_env = archive["storage"].get("url_env_var", "METABLOOMS_RUNTIME_URL")
    url = os.environ.get(url_env)
    artifact_dir = REPO_ROOT / "artifacts"
    target = artifact_dir / archive["filename"]
    if url:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        print(f"[metablooms] fetching runtime asset from {url_env}")
        with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out)
        return target
    for rel in archive["storage"].get("local_fallbacks", []):
        candidate = REPO_ROOT / rel
        if candidate.is_file():
            return candidate
    if target.is_file():
        return target
    return None


def verify_archive(path: Path, expected_sha256: str) -> dict[str, Any]:
    actual = sha256_file(path)
    return {
        "path": str(path),
        "sha256": actual,
        "expected_sha256": expected_sha256,
        "sha256_matches": actual.lower() == expected_sha256.lower(),
    }


def list_archive(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    names: list[str] = []
    try:
        with tarfile.open(path, "r:*") as tf:
            for member in tf.getmembers():
                names.append(member.name)
                if not member_name_safe(member.name):
                    errors.append(f"unsafe_member:{member.name}")
                if member.issym() or member.islnk():
                    errors.append(f"link_member_not_allowed:{member.name}")
    except Exception as exc:
        errors.append(f"python_tar_unavailable:{type(exc).__name__}:{exc}")
    if names:
        return names, errors

    try:
        cp = subprocess.run(["tar", "-tf", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    except Exception as exc:
        return names, [*errors, f"system_tar_unavailable:{type(exc).__name__}:{exc}"]
    if cp.returncode != 0:
        return names, [*errors, f"system_tar_exit:{cp.returncode}:{cp.stderr.strip()[:500]}"]
    names = [line for line in cp.stdout.splitlines() if line.strip()]
    errors = []
    for name in names:
        if not member_name_safe(name):
            errors.append(f"unsafe_member:{name}")
    return names, errors


def extract_archive(path: Path, destination: Path, top_level: str) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    names, errors = list_archive(path)
    if errors:
        raise SystemExit("BLOCKED unsafe or unreadable archive: " + "; ".join(errors[:8]))
    if not any(name.rstrip("/") == top_level for name in names):
        raise SystemExit(f"BLOCKED archive does not contain top-level {top_level}")

    with tempfile.TemporaryDirectory(prefix="metablooms_extract_") as raw:
        staging = Path(raw)
        cp = subprocess.run(["tar", "-xf", str(path), "-C", str(staging)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
        if cp.returncode != 0:
            raise SystemExit(f"BLOCKED extraction failed: {cp.stderr.strip()[:1000]}")
        extracted_root = staging / top_level
        if not extracted_root.is_dir():
            raise SystemExit(f"BLOCKED extracted root missing: {extracted_root}")
        final_root = destination / top_level
        if final_root.exists():
            shutil.rmtree(final_root)
        shutil.move(str(extracted_root), str(final_root))
        return final_root


def runtime_status(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    boot_entry = root / manifest["boot"]["entrypoint"].split("/", 1)[1]
    sentinels = [
        root / "boot.py",
        root / "BOOT_THIS_BUNDLE_START_HERE.md",
        root / "CURRENT_CONTINUATION_STATE_v1.json",
        root / "runtime",
        root / "0_kernel",
    ]
    return {
        "root": str(root),
        "boot_entry": str(boot_entry),
        "boot_entry_exists": boot_entry.is_file(),
        "sentinels": {str(path.relative_to(root)): path.exists() for path in sentinels},
    }


def boot_runtime(root: Path, manifest: dict[str, Any], safe_probe: bool) -> int:
    boot_entry = root / manifest["boot"]["entrypoint"].split("/", 1)[1]
    args = manifest["boot"]["safe_probe_args"] if safe_probe else manifest["boot"]["full_boot_args"]
    cmd = [sys.executable, str(boot_entry), *args]
    cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(root), timeout=600)
    print(cp.stdout)
    if cp.stderr:
        print(cp.stderr, file=sys.stderr)
    return cp.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch, verify, extract, and boot MetaBlooms OS from a GitHub repo.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--work-dir", default=str(REPO_ROOT / "runtime_work"))
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--boot", action="store_true")
    parser.add_argument("--full-boot", action="store_true")
    parser.add_argument("--receipt", default=str(REPO_ROOT / "runtime_work" / "METABLOOMS_RUNTIME_RECEIPT.json"))
    args = parser.parse_args(argv)

    manifest = read_json(Path(args.manifest))
    archive = locate_archive(manifest)
    if not archive:
        raise SystemExit("BLOCKED runtime archive missing. Set METABLOOMS_RUNTIME_URL or place the archive in artifacts/.")

    archive_meta = manifest["runtime_archive"]
    verification = verify_archive(archive, archive_meta["sha256"])
    if not verification["sha256_matches"]:
        write_json(Path(args.receipt), {"verdict": "BLOCKED", "verification": verification})
        raise SystemExit("BLOCKED runtime SHA-256 mismatch")

    names, errors = list_archive(archive)
    if errors:
        write_json(Path(args.receipt), {"verdict": "BLOCKED", "verification": verification, "archive_errors": errors})
        raise SystemExit("BLOCKED archive member validation failed")

    root = None
    if args.extract or args.boot or args.full_boot:
        root = extract_archive(archive, Path(args.work_dir), archive_meta["top_level_directory"])

    status = runtime_status(root, manifest) if root else None
    boot_exit_code = None
    if args.boot or args.full_boot:
        boot_exit_code = boot_runtime(root, manifest, safe_probe=not args.full_boot)

    receipt = {
        "schema": "mb.github_runtime.receipt.v1",
        "verdict": "PASS" if boot_exit_code in (None, 0) else "BLOCKED",
        "archive": verification,
        "archive_member_count": len(names),
        "runtime_status": status,
        "boot_exit_code": boot_exit_code,
    }
    write_json(Path(args.receipt), receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
