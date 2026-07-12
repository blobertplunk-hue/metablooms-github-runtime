from __future__ import annotations

import json
import subprocess
from pathlib import Path

from metablooms_sandbox_factory.factory_common import sha256_file, write_sidecar


def build_tar_zst(source_root: Path, output: Path) -> dict[str, str | int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    parent = source_root.parent
    name = source_root.name
    cmd = [
        "tar",
        "-acf",
        str(output),
        "--exclude=__pycache__",
        "--exclude=*.pyc",
        "--exclude=*.pyo",
        "-C",
        str(parent),
        name,
    ]
    cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if cp.returncode != 0:
        raise RuntimeError(f"tar failed: {cp.stderr[-2000:]}")
    write_sidecar(output)
    return {
        "output": str(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--source-root", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = build_tar_zst(Path(args.source_root), Path(args.output))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
