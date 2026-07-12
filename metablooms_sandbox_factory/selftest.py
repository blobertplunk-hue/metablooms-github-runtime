from __future__ import annotations

import json
import tempfile
from pathlib import Path

from metablooms_sandbox_factory.factory_common import sha256_file, write_json, write_sidecar
from metablooms_sandbox_factory.packaging.verify_artifact import verify_archive
from metablooms_sandbox_factory.repair.blocker_worklist import build_worklist


def test_repair_worklist(tmp: Path) -> None:
    blockers = [
        {
            "tool": "ruff",
            "rule_id": "F821",
            "path": "a.py",
            "line": 10,
            "message": "Undefined name `_mb_write_json_file`",
            "root_cause_category": "undefined_name",
        },
        {
            "tool": "mypy",
            "rule_id": "name-defined",
            "path": "a.py",
            "line": 10,
            "message": "Name \"_mb_write_json_file\" is not defined",
            "root_cause_category": "undefined_name",
        },
    ]
    path = tmp / "BLOCKERS.json"
    write_json(path, blockers)
    worklist = build_worklist(path, tmp / "repair")
    assert worklist["blocker_count"] == 2
    assert worklist["symbol_counts"]["_mb_write_json_file"] == 2


def test_sidecar(tmp: Path) -> None:
    f = tmp / "x.txt"
    f.write_text("hello\n", encoding="utf-8")
    side = write_sidecar(f)
    assert side.is_file()
    assert side.read_text(encoding="ascii").split()[0] == sha256_file(f)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        test_repair_worklist(tmp)
        test_sidecar(tmp)
    print(json.dumps({"SELFTEST_DECISION": "PASS", "tests": 2}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
