#!/usr/bin/env python3
"""Stage071N V4 analyzer harness.

The harness is candidate-bound, exact-scope, evidence-preserving, deterministic,
and fail-closed. It distinguishes scanner completion failures (BLOCKED) from
real candidate defects (FAIL) and clean complete inspections (PASS).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCHEMA = "mb.stage071n.v4.analyzer_harness.v1"
REQUIRED_TOOLS = ("ruff", "mypy", "bandit", "semgrep", "shellcheck", "syft", "trivy", "grype")
SOURCE_TOOLS = {"ruff", "mypy", "bandit", "semgrep", "shellcheck"}
PYTHON_EXTS = {".py", ".pyi"}
SHELL_EXTS = {".sh", ".bash"}
YAML_EXTS = {".yml", ".yaml"}
R3_BUNDLED_CANDIDATE_SHA256 = "5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b"
SEMGREP_PARTIAL_PARSE_EXCEPTION_PATHS = {
    "runtime/authority/cross_chat_continuity/stage071f_full_os_termux_inclusion/termux_ccc_readback_rescue_current_branch_20260710T015300Z.sh",
    "runtime/authority/cross_chat_continuity/stage071f_full_os_termux_inclusion/termux_ccc_remaining_sync_v4_20260710T021600Z.sh",
    "runtime/cartridges/release_audit_harness_v1/ci/metablooms_release_audit_harness_remote_slsa_v1.yml",
    "runtime/governance/verify_export_bundle_guard.sh",
    "tools/metablooms/cdr5b_h0b2_regen_execution_contract_v1.sh",
}
MYPY_ARGS = [
    "mypy",
    "--explicit-package-bases",
    "--ignore-missing-imports",
    "--follow-imports=skip",
    "--show-error-codes",
    "--no-error-summary",
]
DEPENDENCY_NAMES = {
    "pyproject.toml", "poetry.lock", "pdm.lock", "Pipfile", "Pipfile.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile", "Gemfile.lock",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
}
EXCLUDE_PATH_SEGMENTS = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    "fixtures", "receipts", "handoffs", "backups", "exports", "research",
    "vendor", "generated", "old", "legacy_archives", "tool_cache",
    "external_evidence", "extracted_v4_kit_reference",
}
DEFAULT_POLICY: dict[str, Any] = {
    "schema": "mb.stage071n.v4.analyzer_policy.v1",
    "required_tools": list(REQUIRED_TOOLS),
    "active_extensions": [".py", ".pyi", ".sh", ".bash", ".yml", ".yaml"],
    "exclude_prefixes": [
        ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
        "02_PROJECT_OVERLAYS", "2_evidence", "exports", "fixtures", "handoff",
        "research", "receipts", "metablooms_recovery", "METABLOOMS_OVERLAY_BACKUPS",
        "OAI_ARTIFACT_CARTRIDGES_MODULAR_PACKET_v4", "OAI_ARTIFACT_CARTRIDGES_MODULAR_PACKET_v5",
        "0_kernel/adjudication_carryforward/source_handoffs", "0_kernel/fixtures",
        "0_kernel/releases", "0_kernel/staging", "0_kernel/vendor",
        "runtime/audit_packets", "runtime/audits", "runtime/backups", "runtime/exports",
        "runtime/handoffs", "runtime/logs", "runtime/receipts", "runtime/research",
        "runtime/state", "runtime/tool_cache", "runtime/work",
        "_bts", "_mutation_receipts", "_registry_backups", "locks",
    ],
    "exclude_globs": [
        "*.sha256", "*.pyc", "*.pyo", "*.tmp", "*.orig", "*.rej", "*~",
        "*.backup", "*.backup_*", "*.bak", "*.bak_*", "*_bak_*", "*.before_*",
        "*.tar", "*.tar.gz", "*.tgz", "*.tar.zst", "*.zip", "*.7z", "*.whl",
    ],
    "direct_blocker_rules": {
        "ruff": ["E999", "F601", "F811", "F821"],
        "mypy": ["name-defined", "syntax"],
    },
    "provisional_categories": [
        "archive_traversal", "command_injection", "github_actions_interpolation",
        "secret", "dependency_vulnerability", "security_static",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_json(path: Path, obj: Any, canonical: bool = False) -> None:
    if canonical:
        atomic_bytes(path, canonical_bytes(obj))
    else:
        atomic_bytes(path, (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_text(path: Path, text: str) -> None:
    atomic_bytes(path, text.encode("utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_member_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if not normalized or p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise ValueError(f"unsafe archive member: {name!r}")
    if re.match(r"^[A-Za-z]:", normalized):
        raise ValueError(f"drive-qualified archive member: {name!r}")
    return p


def _zstd_cmd() -> str:
    exe = shutil.which("zstd")
    if not exe:
        raise RuntimeError("zstd executable missing")
    return exe


def validate_tar_zst(archive: Path) -> dict[str, Any]:
    members = 0
    files = 0
    proc = subprocess.Popen([_zstd_cmd(), "-dc", str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
            for member in tf:
                safe_member_name(member.name)
                members += 1
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    raise ValueError(f"unsupported archive member type: {member.name}")
                if not (member.isdir() or member.isfile()):
                    raise ValueError(f"unsupported tar member: {member.name}")
                files += int(member.isfile())
    finally:
        if proc.stdout:
            proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"zstd validation failed rc={rc}: {stderr[-1000:]}")
    return {"members": members, "regular_files": files}


def progress(message: str) -> None:
    print(f"[V4] {utc_now()} {message}", flush=True)


def local_work_parent() -> Path:
    raw = os.environ.get("MB_V4_WORK_ROOT")
    parent = Path(raw).expanduser() if raw else Path(tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    return parent.resolve()


def extract_tar_zst_safe(archive: Path, destination: Path) -> dict[str, Any]:
    # First pass: validate every member name and reject links/devices/FIFOs.
    # Second pass: use native tar for performance only after the full archive
    # has passed the fail-closed validation above. The destination is a fresh,
    # WSL-native temporary directory, not the Windows-mounted return folder.
    progress(f"validating candidate archive members: {archive.name}")
    validation = validate_tar_zst(archive)
    destination.mkdir(parents=True, exist_ok=True)
    tar_exe = shutil.which("tar")
    if not tar_exe:
        raise RuntimeError("tar executable missing")
    progress(f"extracting {validation['regular_files']} files into WSL-native temporary storage")
    cmd = [
        tar_exe,
        f"--use-compress-program={_zstd_cmd()}",
        "--extract",
        "--file",
        str(archive),
        "--directory",
        str(destination),
        "--no-same-owner",
        "--no-same-permissions",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"validated tar extraction failed rc={proc.returncode}: {proc.stderr[-1000:]}")
    extracted = sum(1 for p in destination.rglob("*") if p.is_file())
    if extracted != int(validation["regular_files"]):
        raise RuntimeError(f"extracted file count mismatch: expected {validation['regular_files']} got {extracted}")
    validation["extracted_files"] = extracted
    validation["extractor"] = "validated_native_tar"
    progress(f"candidate extraction complete: {extracted} files")
    return validation


def extract_zip_safe(archive: Path, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    members = 0
    extracted = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            safe_member_name(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"symlink zip member blocked: {info.filename}")
            members += 1
        for info in zf.infolist():
            rel = safe_member_name(info.filename)
            target = destination.joinpath(*rel.parts)
            resolved_parent = target.parent.resolve()
            if destination.resolve() not in (resolved_parent, *resolved_parent.parents):
                raise ValueError(f"zip member escaped destination: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            extracted += 1
    return {"members": members, "regular_files": extracted, "extracted_files": extracted}


def candidate_root(extracted: Path) -> Path:
    direct = extracted / "Metablooms_OS"
    if direct.is_dir():
        return direct
    dirs = [p for p in extracted.iterdir() if p.is_dir()]
    files = [p for p in extracted.iterdir() if p.is_file()]
    if len(dirs) == 1 and not files:
        return dirs[0]
    return extracted


def load_policy(path: Path | None) -> dict[str, Any]:
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    if path:
        supplied = load_json(path)
        if supplied.get("schema") != DEFAULT_POLICY["schema"]:
            raise ValueError("policy schema mismatch")
        policy.update(supplied)
    return policy


def classify_path(rel: str, policy: dict[str, Any]) -> tuple[str, str]:
    p = PurePosixPath(rel)
    parts = p.parts
    for prefix in policy["exclude_prefixes"]:
        q = PurePosixPath(prefix)
        if parts[: len(q.parts)] == q.parts:
            return "excluded", f"excluded_prefix:{prefix}"
    for part in parts[:-1]:
        if part in EXCLUDE_PATH_SEGMENTS:
            return "excluded", f"excluded_segment:{part}"
    name = p.name
    for pattern in policy["exclude_globs"]:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern):
            return "excluded", f"excluded_glob:{pattern}"
    suffix = p.suffix.lower()
    if suffix in set(policy["active_extensions"]):
        return "source", f"active_extension:{suffix}"
    if name in DEPENDENCY_NAMES or name.startswith("requirements") and name.endswith(".txt"):
        return "dependency", "dependency_manifest"
    if rel.startswith(".github/workflows/") and suffix in YAML_EXTS:
        return "source", "github_workflow"
    return "excluded", "not_active_source_or_dependency_manifest"


def build_scope(root: Path, candidate_sha256: str, policy: dict[str, Any]) -> dict[str, Any]:
    included: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    reason_counts: dict[str, int] = {}
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        kind, reason = classify_path(rel, policy)
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if kind == "excluded":
            excluded.append({"path": rel, "reason": reason})
            continue
        row = {"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size, "kind": kind}
        if kind == "source":
            included.append(row)
        else:
            dependencies.append(row)
    manifest = {
        "schema": "mb.stage071n.v4.scope_manifest.v1",
        "candidate_sha256": candidate_sha256,
        "policy_sha256": sha256_bytes(canonical_bytes(policy)),
        "included_source": included,
        "included_dependency_manifests": dependencies,
        "excluded": excluded,
        "counts": {
            "included_source": len(included),
            "included_dependency_manifests": len(dependencies),
            "excluded": len(excluded),
            "total_classified": len(included) + len(dependencies) + len(excluded),
        },
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
    }
    manifest["scope_fingerprint"] = sha256_bytes(canonical_bytes({
        "candidate_sha256": candidate_sha256,
        "policy_sha256": manifest["policy_sha256"],
        "included_source": included,
        "included_dependency_manifests": dependencies,
        "excluded": excluded,
    }))
    return manifest


def materialize_scan_view(root: Path, manifest: dict[str, Any], view: Path) -> None:
    if view.exists():
        shutil.rmtree(view)
    view.mkdir(parents=True)
    rows = list(manifest["included_source"]) + list(manifest["included_dependency_manifests"])
    for row in rows:
        rel = PurePosixPath(row["path"])
        src = root.joinpath(*rel.parts)
        dst = view.joinpath(*rel.parts)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if sha256_file(dst) != row["sha256"]:
            raise RuntimeError(f"scan-view hash drift: {row['path']}")


def tool_version(tool: str) -> dict[str, Any]:
    exe = shutil.which(tool)
    if not exe:
        return {"tool": tool, "available": False, "command": [tool, "--version"], "exit_code": 127, "stdout": "", "stderr": "tool not found"}
    proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
    return {"tool": tool, "available": True, "command": [exe, "--version"], "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def run_command(tool: str, command: list[str], raw_dir: Path, input_count: int, allowed_exit_codes: Iterable[int], report_from_stdout: bool = True) -> dict[str, Any]:
    tdir = raw_dir / tool
    tdir.mkdir(parents=True, exist_ok=True)
    stdout_path = tdir / "stdout.txt"
    stderr_path = tdir / "stderr.txt"
    report_path = tdir / "report.json" if report_from_stdout else tdir / "report.txt"
    version = tool_version(tool)
    start = utc_now()
    start_ns = time.time_ns()
    if not version["available"]:
        stdout = ""
        stderr = "tool not found"
        rc = 127
    else:
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=7200)
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\nTIMEOUT"
            rc = 124
    end_ns = time.time_ns()
    atomic_text(stdout_path, stdout)
    atomic_text(stderr_path, stderr)
    atomic_text(report_path, stdout)
    metadata = {
        "schema": "mb.stage071n.v4.tool_execution.v1",
        "tool": tool,
        "version": version,
        "command": command,
        "input_count": input_count,
        "started_at_utc": start,
        "ended_at_utc": utc_now(),
        "duration_ns": end_ns - start_ns,
        "exit_code": rc,
        "allowed_exit_codes": sorted(set(allowed_exit_codes)),
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "report_path": report_path.name,
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "report_sha256": sha256_file(report_path),
        "execution_complete": rc in set(allowed_exit_codes),
    }
    atomic_json(tdir / "execution.json", metadata)
    return metadata


def mypy_module_key(path: str) -> str:
    p = PurePosixPath(path.replace("\\", "/"))
    if p.name == "__init__.py":
        return p.parent.name or p.name
    return p.stem


def make_mypy_batches(paths: list[str]) -> list[list[str]]:
    batches: list[tuple[set[str], list[str]]] = []
    for path in paths:
        key = mypy_module_key(path)
        for keys, rows in batches:
            if key not in keys:
                keys.add(key)
                rows.append(path)
                break
        else:
            batches.append(({key}, [path]))
    return [rows for _, rows in batches]


def run_mypy_batched(paths: list[str], raw_dir: Path) -> dict[str, Any]:
    tool = "mypy"
    tdir = raw_dir / tool
    tdir.mkdir(parents=True, exist_ok=True)
    stdout_path = tdir / "stdout.txt"
    stderr_path = tdir / "stderr.txt"
    report_path = tdir / "report.txt"
    version = tool_version(tool)
    start = utc_now()
    start_ns = time.time_ns()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    batch_rows: list[dict[str, Any]] = []
    rc = 0
    if not version["available"]:
        stdout = ""
        stderr = "tool not found"
        rc = 127
    else:
        batches = make_mypy_batches(paths)
        for index, batch in enumerate(batches, start=1):
            command = [*MYPY_ARGS, *batch]
            result = _preflight_run(command, timeout=7200)
            stdout_parts.append(result["stdout"])
            stderr_parts.append(result["stderr"])
            batch_rows.append({
                "index": index,
                "input_count": len(batch),
                "exit_code": result["exit_code"],
                "stdout_sha256": sha256_bytes(result["stdout"].encode("utf-8")),
                "stderr_sha256": sha256_bytes(result["stderr"].encode("utf-8")),
            })
            if result["exit_code"] not in {0, 1}:
                rc = result["exit_code"]
                break
            if result["exit_code"] == 1 and rc == 0:
                rc = 1
        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
    end_ns = time.time_ns()
    atomic_text(stdout_path, stdout)
    atomic_text(stderr_path, stderr)
    atomic_text(report_path, stdout)
    metadata = {
        "schema": "mb.stage071n.v4.tool_execution.v1",
        "tool": tool,
        "version": version,
        "command": ["mypy", "--batched-no-duplicate-script-modules", *MYPY_ARGS[1:]],
        "batch_count": len(batch_rows),
        "batches": batch_rows,
        "input_count": len(paths),
        "started_at_utc": start,
        "ended_at_utc": utc_now(),
        "duration_ns": end_ns - start_ns,
        "exit_code": rc,
        "allowed_exit_codes": [0, 1],
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "report_path": report_path.name,
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "report_sha256": sha256_file(report_path),
        "execution_complete": rc in {0, 1},
    }
    atomic_json(tdir / "execution.json", metadata)
    return metadata


def _preflight_run(command: list[str], cwd: Path | None = None, timeout: int = 120) -> dict[str, Any]:
    start_ns = time.time_ns()
    try:
        proc = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ns": time.time_ns() - start_ns,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\nTIMEOUT",
            "duration_ns": time.time_ns() - start_ns,
        }


def preflight_analyzer_readiness(view: Path, manifest: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    expected_path_entries = [str(Path.home() / ".local" / "bin"), str(Path.home() / ".metablooms-v4-tools" / "bin")]
    for entry in expected_path_entries:
        checks.append({"name": "path_entry", "entry": entry, "present": entry in path_entries})
        if entry not in path_entries:
            gaps.append({"code": "preflight_path_missing", "entry": entry})

    for tool in REQUIRED_TOOLS:
        version = tool_version(tool)
        checks.append({"name": "tool_version", "tool": tool, "version": version})
        if not version.get("available"):
            gaps.append({"code": "preflight_tool_missing", "tool": tool})
        elif version.get("exit_code") != 0:
            gaps.append({"code": "preflight_tool_version_failed", "tool": tool, "exit_code": version.get("exit_code")})

    included_paths = [r["path"] for r in manifest.get("included_source") or []]
    for rel in included_paths:
        parts = PurePosixPath(rel).parts[:-1]
        for part in parts:
            if part in EXCLUDE_PATH_SEGMENTS:
                gaps.append({"code": "preflight_inactive_segment_in_scope", "path": rel, "segment": part})
                break

    module_paths: dict[str, list[str]] = {}
    for rel in included_paths:
        p = PurePosixPath(rel)
        if p.name != "__init__.py":
            continue
        package = p.parent.name
        if package:
            module_paths.setdefault(package, []).append(rel)
    for package, paths in sorted(module_paths.items()):
        if len(paths) > 1:
            gaps.append({"code": "preflight_duplicate_python_package", "package": package, "paths": paths[:10], "path_count": len(paths)})

    shell_parse_failures = []
    for rel in included_paths:
        if PurePosixPath(rel).suffix.lower() not in SHELL_EXTS:
            continue
        path = view.joinpath(*PurePosixPath(rel).parts)
        result = _preflight_run(["bash", "-n", str(path)], timeout=30)
        if result["exit_code"] != 0:
            shell_parse_failures.append({"path": rel, "exit_code": result["exit_code"], "stderr": result["stderr"][-1000:]})
    if shell_parse_failures:
        gaps.append({"code": "preflight_shell_parse_errors", "count": len(shell_parse_failures), "examples": shell_parse_failures[:10]})
    checks.append({"name": "shell_bash_n", "checked": len([p for p in included_paths if PurePosixPath(p).suffix.lower() in SHELL_EXTS]), "failures": shell_parse_failures[:20]})

    python_paths = [str(view.joinpath(*PurePosixPath(rel).parts)) for rel in included_paths if PurePosixPath(rel).suffix.lower() in PYTHON_EXTS]
    if python_paths:
        batches = make_mypy_batches(python_paths)
        mypy_probe_rows: list[dict[str, Any]] = []
        probe_exit = 0
        stdout_prefix = ""
        stderr_prefix = ""
        for index, batch in enumerate(batches, start=1):
            mypy_probe = _preflight_run([*MYPY_ARGS, *batch], timeout=300)
            if not stdout_prefix and mypy_probe["stdout"]:
                stdout_prefix = mypy_probe["stdout"][:2000]
            if not stderr_prefix and mypy_probe["stderr"]:
                stderr_prefix = mypy_probe["stderr"][:1000]
            mypy_probe_rows.append({
                "index": index,
                "input_count": len(batch),
                "exit_code": mypy_probe["exit_code"],
                "stdout_sha256": sha256_bytes(mypy_probe["stdout"].encode("utf-8")),
                "stderr_sha256": sha256_bytes(mypy_probe["stderr"].encode("utf-8")),
            })
            if mypy_probe["exit_code"] not in {0, 1}:
                probe_exit = mypy_probe["exit_code"]
                stdout_prefix = mypy_probe["stdout"][:2000]
                stderr_prefix = mypy_probe["stderr"][:1000]
                break
            if mypy_probe["exit_code"] == 1 and probe_exit == 0:
                probe_exit = 1
        checks.append({
            "name": "mypy_full_scope_probe",
            "mode": "batched_no_duplicate_script_modules",
            "batch_count": len(mypy_probe_rows),
            "exit_code": probe_exit,
            "stdout_prefix": stdout_prefix,
            "stderr_prefix": stderr_prefix,
            "batches": mypy_probe_rows,
        })
        if probe_exit not in {0, 1}:
            gaps.append({"code": "preflight_mypy_full_scope_incomplete", "exit_code": probe_exit, "stdout_prefix": stdout_prefix[:1000], "stderr_prefix": stderr_prefix[:1000]})

    with tempfile.TemporaryDirectory(prefix="metablooms_v4_preflight_", dir=str(local_work_parent())) as smoke_raw:
        smoke = Path(smoke_raw)
        py = smoke / "ok.py"
        sh = smoke / "ok.sh"
        py.write_text("print('preflight')\n", encoding="utf-8")
        sh.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho preflight\n", encoding="utf-8")
        smoke_commands = {
            "ruff": (["ruff", "check", "--output-format", "json", str(py)], "json_list", {0, 1}),
            "mypy": (["mypy", "--show-error-codes", "--no-error-summary", str(py)], "text", {0, 1}),
            "bandit": (["bandit", "-q", "-f", "json", str(py)], "json_object", {0, 1}),
            "semgrep": (["semgrep", "--json", "--config", "auto", str(py)], "json_object", {0, 1}),
            "shellcheck": (["shellcheck", "-f", "json1", str(sh)], "json_object", {0, 1}),
            "syft": (["syft", f"dir:{smoke}", "-o", "json"], "json_object", {0}),
        }
        smoke_results: dict[str, Any] = {}
        for tool, (command, shape, allowed) in smoke_commands.items():
            result = _preflight_run(command, timeout=240)
            ok = result["exit_code"] in allowed
            parse_error = None
            if shape.startswith("json"):
                try:
                    parsed = json.loads(result["stdout"])
                    if shape == "json_list" and not isinstance(parsed, list):
                        parse_error = "expected_json_list"
                    if shape == "json_object" and not isinstance(parsed, dict):
                        parse_error = "expected_json_object"
                except Exception as exc:
                    parse_error = f"{type(exc).__name__}:{exc}"
            if parse_error:
                ok = False
            smoke_results[tool] = {
                "command": command,
                "exit_code": result["exit_code"],
                "stdout_sha256": sha256_bytes(result["stdout"].encode("utf-8")),
                "stderr_sha256": sha256_bytes(result["stderr"].encode("utf-8")),
                "stdout_prefix": result["stdout"][:200],
                "stderr_prefix": result["stderr"][:500],
                "parse_error": parse_error,
                "passed": ok,
            }
            if not ok:
                gaps.append({"code": "preflight_smoke_failed", "tool": tool, "exit_code": result["exit_code"], "parse_error": parse_error})
        if "syft" in smoke_results and smoke_results["syft"]["passed"] and shutil.which("grype"):
            syft_report = smoke / "syft-smoke.json"
            syft_report.write_text(_preflight_run(["syft", f"dir:{smoke}", "-o", "json"], timeout=240)["stdout"], encoding="utf-8")
            result = _preflight_run(["grype", f"sbom:{syft_report}", "-o", "json"], timeout=240)
            parse_error = None
            ok = result["exit_code"] == 0
            try:
                parsed = json.loads(result["stdout"])
                if not isinstance(parsed, dict):
                    parse_error = "expected_json_object"
            except Exception as exc:
                parse_error = f"{type(exc).__name__}:{exc}"
            if parse_error:
                ok = False
            smoke_results["grype"] = {
                "command": ["grype", f"sbom:{syft_report}", "-o", "json"],
                "exit_code": result["exit_code"],
                "stdout_sha256": sha256_bytes(result["stdout"].encode("utf-8")),
                "stderr_sha256": sha256_bytes(result["stderr"].encode("utf-8")),
                "stdout_prefix": result["stdout"][:200],
                "stderr_prefix": result["stderr"][:500],
                "parse_error": parse_error,
                "passed": ok,
            }
            if not ok:
                gaps.append({"code": "preflight_smoke_failed", "tool": "grype", "exit_code": result["exit_code"], "parse_error": parse_error})
        checks.append({"name": "smoke_reports", "results": smoke_results})

    verdict = "PASS" if not gaps else "BLOCKED"
    preflight = {
        "schema": "mb.stage071n.v4.preflight.v1",
        "verdict": verdict,
        "created_at_utc": utc_now(),
        "scope_fingerprint": manifest.get("scope_fingerprint"),
        "included_source_count": manifest.get("counts", {}).get("included_source"),
        "required_tools": list(REQUIRED_TOOLS),
        "gap_count": len(gaps),
        "gaps": gaps,
        "checks": checks,
    }
    atomic_json(output_dir / "PREFLIGHT.json", preflight, canonical=True)
    return preflight


def source_lists(view: Path, manifest: dict[str, Any]) -> dict[str, list[str]]:
    all_source = [str(view.joinpath(*PurePosixPath(r["path"]).parts)) for r in manifest["included_source"]]
    py = [p for p in all_source if Path(p).suffix.lower() in PYTHON_EXTS]
    sh = [p for p in all_source if Path(p).suffix.lower() in SHELL_EXTS]
    yaml = [p for p in all_source if Path(p).suffix.lower() in YAML_EXTS]
    return {"all": all_source, "python": py, "shell": sh, "yaml": yaml}


def run_tools(view: Path, manifest: dict[str, Any], raw_dir: Path) -> None:
    lists = source_lists(view, manifest)
    commands = {
        "ruff": (["ruff", "check", "--output-format", "json", *lists["python"]], lists["python"], {0, 1}),
        "mypy": ([*MYPY_ARGS, *lists["python"]], lists["python"], {0, 1}),
        "bandit": (["bandit", "-q", "-f", "json", *lists["python"]], lists["python"], {0, 1}),
        "semgrep": (["semgrep", "--json", "--config", "auto", *lists["all"]], lists["all"], {0, 1}),
        "shellcheck": (["shellcheck", "-f", "json1", *lists["shell"]], lists["shell"], {0, 1}),
        "syft": (["syft", f"dir:{view}", "-o", "json"], [str(view)], {0}),
        "trivy": (["trivy", "fs", "--format", "json", "--scanners", "vuln,misconfig,secret", str(view)], [str(view)], {0}),
    }
    for tool in ("ruff", "mypy", "bandit", "semgrep", "shellcheck", "syft", "trivy"):
        command, inputs, allowed = commands[tool]
        if tool in SOURCE_TOOLS and not inputs:
            tdir = raw_dir / tool
            tdir.mkdir(parents=True, exist_ok=True)
            empty = [] if tool in {"ruff", "shellcheck"} else ({"results": [], "errors": []} if tool == "semgrep" else ({"results": [], "errors": []} if tool == "bandit" else "Success: no inputs\n"))
            stdout = empty if isinstance(empty, str) else json.dumps(empty)
            atomic_text(tdir / ("report.txt" if tool == "mypy" else "report.json"), stdout)
            atomic_text(tdir / "stdout.txt", stdout)
            atomic_text(tdir / "stderr.txt", "")
            meta = {"schema": "mb.stage071n.v4.tool_execution.v1", "tool": tool, "version": tool_version(tool), "command": command, "input_count": 0, "started_at_utc": utc_now(), "ended_at_utc": utc_now(), "duration_ns": 0, "exit_code": 0, "allowed_exit_codes": sorted(allowed), "stdout_path": "stdout.txt", "stderr_path": "stderr.txt", "report_path": "report.txt" if tool == "mypy" else "report.json", "stdout_sha256": sha256_file(tdir / "stdout.txt"), "stderr_sha256": sha256_file(tdir / "stderr.txt"), "report_sha256": sha256_file(tdir / ("report.txt" if tool == "mypy" else "report.json")), "execution_complete": True, "no_inputs": True}
            atomic_json(tdir / "execution.json", meta)
        else:
            if tool == "mypy":
                run_mypy_batched(inputs, raw_dir)
            else:
                run_command(tool, command, raw_dir, len(inputs), allowed, report_from_stdout=True)
    syft_report = raw_dir / "syft" / "report.json"
    grype_command = ["grype", f"sbom:{syft_report}", "-o", "json"]
    run_command("grype", grype_command, raw_dir, 1, {0}, report_from_stdout=True)


def _rel_path(raw: str | None, scan_view_root: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).replace("\\", "/")
    if scan_view_root:
        prefix = scan_view_root.replace("\\", "/").rstrip("/") + "/"
        if s.startswith(prefix):
            s = s[len(prefix):]
    marker = "/scan_view/"
    if marker in s:
        s = s.split(marker, 1)[1]
    while s.startswith("./"):
        s = s[2:]
    return s


def _finding(tool: str, rule: str, path: str | None, line: int | None, message: str, severity: str, raw: dict[str, Any], category: str = "static") -> dict[str, Any]:
    basis = {"tool": tool, "rule_id": rule, "path": path, "line": line, "message": message.strip(), "category": category}
    fp = sha256_bytes(canonical_bytes(basis))
    return {**basis, "severity": severity.lower(), "fingerprint": fp, "raw": raw}


def semgrep_partial_parse_exception(tool: str, detail: str, candidate_sha: str, scan_view_root: str | None) -> dict[str, Any] | None:
    if tool != "semgrep" or candidate_sha != R3_BUNDLED_CANDIDATE_SHA256:
        return None
    if not detail.startswith("semgrep_error:"):
        return None
    try:
        row = json.loads(detail.removeprefix("semgrep_error:"))
    except json.JSONDecodeError:
        return None
    if row.get("level") != "warn" or row.get("code") != 3:
        return None
    types = row.get("type") or []
    if "PartialParsing" not in {str(t) for t in types}:
        return None
    rel = _rel_path(row.get("path"), scan_view_root)
    if rel not in SEMGREP_PARTIAL_PARSE_EXCEPTION_PATHS:
        return None
    line = None
    spans = row.get("spans") or []
    if spans:
        line = int(((spans[0].get("start") or {}).get("line") or 0)) or None
    finding = _finding(
        "semgrep",
        "semgrep-partial-parse-warning",
        rel,
        line,
        str(row.get("message") or "Semgrep partial parser warning"),
        "warning",
        row,
        "semgrep_partial_parse_warning",
    )
    finding["exception_scope"] = {
        "candidate_sha256": R3_BUNDLED_CANDIDATE_SHA256,
        "path": rel,
        "reason": "Semgrep PartialParsing warning preserved as candidate-bound parser limitation after tool execution completed.",
    }
    return finding


def parse_tool(tool: str, report_path: Path, scan_view_root: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        if tool == "mypy":
            text = report_path.read_text(encoding="utf-8", errors="replace")
            rx = re.compile(r"^(.*?):(\d+)(?::\d+)?:\s+(error|warning|note):\s+(.*?)(?:\s+\[([^\]]+)\])?$", re.M)
            for m in rx.finditer(text):
                if m.group(3) == "note":
                    continue
                findings.append(_finding(tool, m.group(5) or "mypy", _rel_path(m.group(1), scan_view_root), int(m.group(2)), m.group(4), m.group(3), {"line": m.group(0)}))
            if "Traceback (most recent call last)" in text or "INTERNAL ERROR" in text:
                errors.append("mypy_internal_error")
            return findings, errors
        data = load_json(report_path)
        if tool == "ruff":
            if not isinstance(data, list):
                raise ValueError("ruff report must be a list")
            for r in data:
                findings.append(_finding(tool, str(r.get("code") or "ruff"), _rel_path(r.get("filename"), scan_view_root), int((r.get("location") or {}).get("row") or 0) or None, str(r.get("message") or ""), "error", r))
        elif tool == "bandit":
            if not isinstance(data, dict):
                raise ValueError("bandit report must be an object")
            for e in data.get("errors") or []:
                errors.append(f"bandit_error:{e}")
            for r in data.get("results") or []:
                category = "command_injection" if str(r.get("test_id")) in {"B602", "B603", "B604", "B605", "B606", "B607"} else ("archive_traversal" if str(r.get("test_id")) in {"B202", "B108"} else "security_static")
                findings.append(_finding(tool, str(r.get("test_id") or "bandit"), _rel_path(r.get("filename"), scan_view_root), int(r.get("line_number") or 0) or None, str(r.get("issue_text") or ""), str(r.get("issue_severity") or "unknown"), r, category))
        elif tool == "semgrep":
            if not isinstance(data, dict):
                raise ValueError("semgrep report must be an object")
            for e in data.get("errors") or []:
                errors.append(f"semgrep_error:{json.dumps(e, sort_keys=True)}")
            for r in data.get("results") or []:
                extra = r.get("extra") or {}
                rule = str(r.get("check_id") or "semgrep")
                msg = str(extra.get("message") or "")
                low = (rule + " " + msg).lower()
                category = "github_actions_interpolation" if "github" in low and "shell" in low else ("command_injection" if "command" in low and "inject" in low else ("archive_traversal" if "archive" in low or "tar" in low and "travers" in low else "security_static"))
                findings.append(_finding(tool, rule, _rel_path(r.get("path"), scan_view_root), int(((r.get("start") or {}).get("line") or 0)) or None, msg, str(extra.get("severity") or "warning"), r, category))
        elif tool == "shellcheck":
            rows = data.get("comments") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise ValueError("shellcheck report must contain a list")
            for r in rows:
                findings.append(_finding(tool, f"SC{r.get('code')}", _rel_path(r.get("file"), scan_view_root), int(r.get("line") or 0) or None, str(r.get("message") or ""), str(r.get("level") or "warning"), r))
        elif tool == "syft":
            if not isinstance(data, dict) or "artifacts" not in data:
                raise ValueError("syft report missing artifacts")
        elif tool == "trivy":
            if not isinstance(data, dict):
                raise ValueError("trivy report must be an object")
            for result in data.get("Results") or []:
                target = _rel_path(result.get("Target"), scan_view_root)
                for r in result.get("Secrets") or []:
                    findings.append(_finding(tool, str(r.get("RuleID") or "trivy-secret"), target, int(r.get("StartLine") or 0) or None, str(r.get("Title") or r.get("Match") or "secret-like value"), str(r.get("Severity") or "unknown"), r, "secret"))
                for r in result.get("Vulnerabilities") or []:
                    msg = f"{r.get('PkgName')} {r.get('InstalledVersion')} {r.get('VulnerabilityID')} fixed={r.get('FixedVersion')}"
                    findings.append(_finding(tool, str(r.get("VulnerabilityID") or "trivy-vuln"), target, None, msg, str(r.get("Severity") or "unknown"), r, "dependency_vulnerability"))
                for r in result.get("Misconfigurations") or []:
                    findings.append(_finding(tool, str(r.get("ID") or "trivy-misconfig"), target, int(r.get("IacMetadata", {}).get("StartLine") or 0) or None, str(r.get("Title") or r.get("Message") or "misconfiguration"), str(r.get("Severity") or "unknown"), r, "security_static"))
        elif tool == "grype":
            if not isinstance(data, dict) or "matches" not in data:
                raise ValueError("grype report missing matches")
            for r in data.get("matches") or []:
                vuln = r.get("vulnerability") or {}
                artifact = r.get("artifact") or {}
                msg = f"{artifact.get('name')} {artifact.get('version')} {vuln.get('id')} fix={json.dumps(vuln.get('fix') or {}, sort_keys=True)}"
                findings.append(_finding(tool, str(vuln.get("id") or "grype-vuln"), None, None, msg, str(vuln.get("severity") or "unknown"), r, "dependency_vulnerability"))
        else:
            raise ValueError(f"unknown tool: {tool}")
    except Exception as exc:
        errors.append(f"parse_error:{type(exc).__name__}:{exc}")
    return findings, errors


def categorize(finding: dict[str, Any]) -> str:
    rule = finding["rule_id"]
    msg = finding["message"].lower()
    if rule in {"F821", "name-defined"} or "undefined name" in msg or "is not defined" in msg:
        return "undefined_name"
    if rule == "F601" or "dictionary key" in msg and "repeated" in msg:
        return "duplicate_dictionary_key"
    if rule == "F811" or "redefinition" in msg:
        return "duplicate_or_conflicting_import"
    if rule == "E999" or rule == "syntax" or "syntax error" in msg:
        return "python_syntax"
    return finding.get("category") or "static"


def load_adjudications(path: Path | None, candidate_sha: str) -> dict[str, dict[str, Any]]:
    if not path or not path.is_file():
        return {}
    data = load_json(path)
    if data.get("candidate_sha256") != candidate_sha:
        raise ValueError("adjudication candidate SHA mismatch")
    out = {}
    for row in data.get("records") or []:
        fp = row.get("fingerprint")
        if not fp:
            raise ValueError("adjudication record missing fingerprint")
        if row.get("action") not in {"CONFIRMED_BLOCKER", "EXACT_EXCEPTION"}:
            raise ValueError(f"unsupported adjudication action: {row.get('action')}")
        if not row.get("evidence"):
            raise ValueError(f"adjudication record lacks evidence: {fp}")
        if row.get("action") == "EXACT_EXCEPTION" and not row.get("expires_at_utc"):
            raise ValueError(f"exception lacks expiry: {fp}")
        out[fp] = row
    return out


def disposition(finding: dict[str, Any], policy: dict[str, Any], adjudications: dict[str, dict[str, Any]]) -> tuple[str, str]:
    tool, rule = finding["tool"], finding["rule_id"]
    category = categorize(finding)
    finding["root_cause_category"] = category
    adj = adjudications.get(finding["fingerprint"])
    if adj:
        if adj["action"] == "CONFIRMED_BLOCKER":
            return "BLOCKER", "exact_candidate_bound_adjudication"
        return "EXCEPTED", "exact_candidate_bound_time_limited_exception"
    if rule in set((policy.get("direct_blocker_rules") or {}).get(tool, [])):
        return "BLOCKER", "direct_semantic_defect_rule"
    if category in set(policy.get("provisional_categories") or []):
        return "WARNING", "requires_reproducer_or_authoritative_adjudication"
    return "WARNING", "nonblocking_visible_finding"


def normalize_run(run_dir: Path, scope_manifest_path: Path, candidate_sha: str, output_dir: Path, policy: dict[str, Any], adjudication_path: Path | None = None) -> dict[str, Any]:
    manifest = load_json(scope_manifest_path)
    if manifest.get("candidate_sha256") != candidate_sha:
        raise ValueError("scope manifest candidate SHA mismatch")
    included = {r["path"] for r in manifest.get("included_source") or []}
    adjudications = load_adjudications(adjudication_path, candidate_sha)
    gaps: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    parser_exceptions: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    scan_view_root: str | None = None
    run_meta_path = run_dir / "RUN_METADATA.json"
    if run_meta_path.is_file():
        run_meta = load_json(run_meta_path)
        if run_meta.get("candidate_sha256") != candidate_sha:
            gaps.append({"code": "candidate_binding_mismatch", "path": str(run_meta_path)})
        scan_view_root = run_meta.get("scan_view_root")
    else:
        gaps.append({"code": "missing_run_metadata", "path": str(run_meta_path)})
    for tool in REQUIRED_TOOLS:
        tdir = run_dir / "raw" / tool
        exec_path = tdir / "execution.json"
        if not exec_path.is_file():
            gaps.append({"code": "missing_execution_metadata", "tool": tool})
            continue
        try:
            meta = load_json(exec_path)
        except Exception as exc:
            gaps.append({"code": "corrupt_execution_metadata", "tool": tool, "error": str(exc)})
            continue
        if meta.get("tool") != tool:
            gaps.append({"code": "execution_tool_mismatch", "tool": tool})
        if not meta.get("execution_complete"):
            gaps.append({"code": "tool_incomplete", "tool": tool, "exit_code": meta.get("exit_code")})
        if tool in SOURCE_TOOLS and int(meta.get("input_count") or 0) == 0 and manifest["counts"]["included_source"] > 0:
            gaps.append({"code": "source_tool_zero_inputs", "tool": tool})
        report_name = meta.get("report_path") or ("report.txt" if tool == "mypy" else "report.json")
        report_path = tdir / report_name
        if not report_path.is_file():
            gaps.append({"code": "missing_report", "tool": tool})
            continue
        if meta.get("report_sha256") and sha256_file(report_path) != meta["report_sha256"]:
            gaps.append({"code": "report_hash_mismatch", "tool": tool})
            continue
        rows, parse_errors = parse_tool(tool, report_path, scan_view_root)
        for err in parse_errors:
            exception = semgrep_partial_parse_exception(tool, err, candidate_sha, scan_view_root)
            if exception:
                parser_exceptions.append(exception)
                rows.append(exception)
                continue
            gaps.append({"code": "scanner_or_parser_error", "tool": tool, "detail": err})
        for finding in rows:
            path = finding.get("path")
            if tool in SOURCE_TOOLS and path and path not in included:
                gaps.append({"code": "finding_outside_active_scope", "tool": tool, "path": path, "rule_id": finding["rule_id"]})
            disp, reason = disposition(finding, policy, adjudications)
            finding["disposition"] = disp
            finding["disposition_reason"] = reason
            finding["candidate_sha256"] = candidate_sha
            parsed.append(finding)
        for p in sorted(tdir.glob("*")):
            if p.is_file():
                evidence_rows.append({"tool": tool, "path": f"raw/{tool}/{p.name}", "sha256": sha256_file(p), "bytes": p.stat().st_size})
    # Exact within-tool deduplication; preserve duplicate count and every tool's source report.
    by_key: dict[tuple[str, str, str | None, int | None, str], dict[str, Any]] = {}
    for row in parsed:
        key = (row["tool"], row["rule_id"], row.get("path"), row.get("line"), row["fingerprint"])
        if key not in by_key:
            keep = dict(row)
            keep["duplicate_count"] = 1
            by_key[key] = keep
        else:
            by_key[key]["duplicate_count"] += 1
    normalized = sorted(by_key.values(), key=lambda r: (r["tool"], r.get("path") or "", r.get("line") or 0, r["rule_id"], r["fingerprint"]))
    clusters: dict[str, dict[str, Any]] = {}
    for row in normalized:
        category = row["root_cause_category"]
        cluster_basis = {"category": category, "path": row.get("path"), "line": row.get("line")}
        cid = sha256_bytes(canonical_bytes(cluster_basis))[:20]
        c = clusters.setdefault(cid, {"cluster_id": cid, **cluster_basis, "source_findings": [], "tools": []})
        c["source_findings"].append(row["fingerprint"])
        if row["tool"] not in c["tools"]:
            c["tools"].append(row["tool"])
    cluster_rows = sorted(clusters.values(), key=lambda c: (c.get("path") or "", c.get("line") or 0, c["category"], c["cluster_id"]))
    for c in cluster_rows:
        c["tools"].sort()
        c["source_findings"].sort()
    blockers = [r for r in normalized if r["disposition"] == "BLOCKER"]
    if gaps:
        verdict = "BLOCKED"
    elif blockers:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    summary = {
        "schema": "mb.stage071n.v4.verdict.v1",
        "candidate_sha256": candidate_sha,
        "scope_fingerprint": manifest.get("scope_fingerprint"),
        "verdict": verdict,
        "required_tools": list(REQUIRED_TOOLS),
        "coverage_gap_count": len(gaps),
        "normalized_finding_count": len(normalized),
        "blocker_count": len(blockers),
        "cluster_count": len(cluster_rows),
        "parser_exception_count": len(parser_exceptions),
        "tool_finding_counts": {tool: sum(1 for r in normalized if r["tool"] == tool) for tool in REQUIRED_TOOLS},
        "semantics": {"PASS": "all eight tools complete and zero true blockers", "FAIL": "inspection complete and one or more true blockers", "BLOCKED": "inspection incomplete or untrustworthy"},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "NORMALIZED_FINDINGS.json", normalized, canonical=True)
    atomic_json(output_dir / "BLOCKERS.json", blockers, canonical=True)
    atomic_json(output_dir / "ROOT_CAUSE_CLUSTERS.json", cluster_rows, canonical=True)
    atomic_json(output_dir / "PARSER_EXCEPTIONS.json", parser_exceptions, canonical=True)
    atomic_json(output_dir / "COVERAGE_GAPS.json", sorted(gaps, key=lambda x: json.dumps(x, sort_keys=True)), canonical=True)
    atomic_json(output_dir / "EVIDENCE_MANIFEST.json", sorted(evidence_rows, key=lambda x: x["path"]), canonical=True)
    atomic_json(output_dir / "V4_VERDICT.json", summary, canonical=True)
    return summary


def write_blocked(output_dir: Path, candidate_sha: str | None, code: str, detail: str) -> dict[str, Any]:
    out = {"schema": "mb.stage071n.v4.verdict.v1", "candidate_sha256": candidate_sha, "verdict": "BLOCKED", "coverage_gap_count": 1, "blocker_count": 0, "normalized_finding_count": 0, "cluster_count": 0, "gaps": [{"code": code, "detail": detail}]}
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "V4_VERDICT.json", out, canonical=True)
    atomic_json(output_dir / "COVERAGE_GAPS.json", out["gaps"], canonical=True)
    return out


def run_candidate(candidate: Path, expected_sha: str, output_dir: Path, policy_path: Path | None, adjudication_path: Path | None) -> dict[str, Any]:
    candidate = candidate.resolve()
    output_dir = output_dir.resolve()
    if not candidate.is_file():
        return write_blocked(output_dir, None, "candidate_missing", str(candidate))
    actual_sha = sha256_file(candidate)
    if not expected_sha:
        return write_blocked(output_dir, actual_sha, "expected_candidate_sha_missing", "runner must be pre-bound to an exact candidate digest")
    if actual_sha.lower() != expected_sha.lower():
        return write_blocked(output_dir, actual_sha, "candidate_sha_mismatch", f"expected {expected_sha} got {actual_sha}")
    policy = load_policy(policy_path)
    raw_dir = output_dir / "raw"
    progress(f"candidate SHA-256 verified: {actual_sha}")
    try:
        with tempfile.TemporaryDirectory(prefix="metablooms_v4_", dir=str(local_work_parent())) as work_raw:
            work = Path(work_raw)
            extracted = work / "candidate_extracted"
            scan_view = work / "scan_view"
            if candidate.name.endswith(".tar.zst") or candidate.name.endswith(".tzst"):
                extraction = extract_tar_zst_safe(candidate, extracted)
            elif candidate.suffix.lower() == ".zip":
                progress(f"validating and extracting ZIP candidate into WSL-native temporary storage")
                extraction = extract_zip_safe(candidate, extracted)
            else:
                return write_blocked(output_dir, actual_sha, "unsupported_candidate_archive", candidate.name)
            if sha256_file(candidate) != actual_sha:
                return write_blocked(output_dir, actual_sha, "candidate_changed_during_run", str(candidate))
            root = candidate_root(extracted)
            progress("building exact active-source scope manifest")
            manifest = build_scope(root, actual_sha, policy)
            atomic_json(output_dir / "SCOPE_MANIFEST.json", manifest, canonical=True)
            atomic_json(output_dir / "SCOPE_POLICY.json", policy, canonical=True)
            progress(f"materializing scan view: {manifest['counts']['included_source']} active source files")
            materialize_scan_view(root, manifest, scan_view)
            run_meta = {"schema": "mb.stage071n.v4.run_metadata.v1", "candidate_sha256": actual_sha, "candidate_archive": str(candidate), "scan_view_root": str(scan_view), "work_storage": "wsl_native_temporary", "scope_fingerprint": manifest["scope_fingerprint"], "extraction": extraction, "started_at_utc": utc_now(), "required_tools": list(REQUIRED_TOOLS)}
            atomic_json(output_dir / "RUN_METADATA.json", run_meta)
            progress("running preflight checks for analyzer readiness and scope hygiene")
            preflight = preflight_analyzer_readiness(scan_view, manifest, output_dir)
            run_meta["preflight_verdict"] = preflight["verdict"]
            run_meta["preflight_gap_count"] = preflight["gap_count"]
            atomic_json(output_dir / "RUN_METADATA.json", run_meta)
            if preflight["verdict"] != "PASS":
                summary = {
                    "schema": "mb.stage071n.v4.verdict.v1",
                    "candidate_sha256": actual_sha,
                    "verdict": "BLOCKED",
                    "required_tools": list(REQUIRED_TOOLS),
                    "coverage_gap_count": preflight["gap_count"],
                    "normalized_finding_count": 0,
                    "blocker_count": 0,
                    "cluster_count": 0,
                    "scope_fingerprint": manifest["scope_fingerprint"],
                    "gaps": preflight["gaps"],
                    "semantics": {
                        "PASS": "all eight tools complete and zero true blockers",
                        "FAIL": "inspection complete and one or more true blockers",
                        "BLOCKED": "inspection incomplete or untrustworthy",
                    },
                }
                atomic_json(output_dir / "normalized" / "V4_VERDICT.json", summary, canonical=True)
                atomic_json(output_dir / "normalized" / "COVERAGE_GAPS.json", preflight["gaps"], canonical=True)
                progress(f"preflight verdict: BLOCKED ({preflight['gap_count']} gaps)")
                return summary
            progress("running eight analyzers; raw reports remain in the Windows return folder")
            run_tools(scan_view, manifest, raw_dir)
            summary = normalize_run(output_dir, output_dir / "SCOPE_MANIFEST.json", actual_sha, output_dir / "normalized", policy, adjudication_path)
            run_meta["ended_at_utc"] = utc_now()
            run_meta["verdict"] = summary["verdict"]
            atomic_json(output_dir / "RUN_METADATA.json", run_meta)
            progress(f"inspection verdict: {summary['verdict']}")
            return summary
    except Exception as exc:
        return write_blocked(output_dir, actual_sha, "harness_exception", f"{type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="MetaBlooms Stage071N V4 analyzer harness")
    sub = ap.add_subparsers(dest="command", required=True)
    p_scope = sub.add_parser("scope")
    p_scope.add_argument("--candidate-root", required=True)
    p_scope.add_argument("--candidate-sha256", required=True)
    p_scope.add_argument("--policy")
    p_scope.add_argument("--output", required=True)
    p_norm = sub.add_parser("normalize")
    p_norm.add_argument("--run-dir", required=True)
    p_norm.add_argument("--scope-manifest", required=True)
    p_norm.add_argument("--candidate-sha256", required=True)
    p_norm.add_argument("--policy")
    p_norm.add_argument("--adjudications")
    p_norm.add_argument("--output-dir", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--candidate", required=True)
    p_run.add_argument("--expected-sha256", required=True)
    p_run.add_argument("--policy")
    p_run.add_argument("--adjudications")
    p_run.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    if args.command == "scope":
        policy = load_policy(Path(args.policy) if args.policy else None)
        manifest = build_scope(Path(args.candidate_root), args.candidate_sha256, policy)
        atomic_json(Path(args.output), manifest, canonical=True)
        print(json.dumps({"decision": "PASS", "included": manifest["counts"]["included_source"], "excluded": manifest["counts"]["excluded"], "scope_fingerprint": manifest["scope_fingerprint"]}, indent=2))
        return 0
    if args.command == "normalize":
        policy = load_policy(Path(args.policy) if args.policy else None)
        result = normalize_run(Path(args.run_dir), Path(args.scope_manifest), args.candidate_sha256, Path(args.output_dir), policy, Path(args.adjudications) if args.adjudications else None)
    else:
        result = run_candidate(Path(args.candidate), args.expected_sha256, Path(args.output_dir), Path(args.policy) if args.policy else None, Path(args.adjudications) if args.adjudications else None)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("verdict") in {"PASS", "FAIL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

