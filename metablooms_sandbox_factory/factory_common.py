from __future__ import annotations

import hashlib
import json
import os
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
RUNS = ROOT / "runs"
INPUT = ROOT / "input"
OUTPUTS = ROOT / "outputs"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_sidecar(path: Path) -> Path:
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{sha256_file(path)}  {path.name}\n", encoding="ascii")
    return sidecar


def ensure_dirs() -> None:
    for p in (RUNS, INPUT, OUTPUTS):
        p.mkdir(parents=True, exist_ok=True)


def safe_members_tar(path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        with tarfile.open(path, "r:*") as tf:
            for member in tf.getmembers():
                name = member.name.replace("\\", "/")
                if name.startswith("/") or "\x00" in name:
                    errors.append(f"unsafe_tar_member:{name}")
                parts = [p for p in name.split("/") if p]
                if any(p == ".." for p in parts):
                    errors.append(f"unsafe_tar_member:{name}")
                if member.issym() or member.islnk():
                    errors.append(f"link_member_not_allowed:{name}")
    except Exception as exc:
        errors.append(f"tar_validation_error:{type(exc).__name__}:{exc}")
    return not errors, errors


def make_return_archive(source_dir: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tf:
        tf.add(source_dir, arcname=source_dir.name)
    write_sidecar(out_path)
    return out_path


def relative_to_workspace(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE.resolve()))
    except ValueError:
        return str(path.resolve())


def path_env() -> dict[str, str]:
    env = os.environ.copy()
    local_bins = [
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".metablooms-v4-tools" / "bin"),
    ]
    env["PATH"] = os.pathsep.join([*local_bins, env.get("PATH", "")])
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return env

