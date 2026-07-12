from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from metablooms_sandbox_factory.factory_common import path_env, utc_now, write_json


REQUIRED_TOOLS = ("ruff", "mypy", "bandit", "semgrep", "shellcheck", "syft", "trivy", "grype")


def probe_tool(name: str) -> dict[str, Any]:
    exe = shutil.which(name, path=path_env().get("PATH"))
    row: dict[str, Any] = {"tool": name, "found": bool(exe), "path": exe}
    if not exe:
        return row
    try:
        cp = subprocess.run([exe, "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, env=path_env())
        row.update({
            "version_exit_code": cp.returncode,
            "version_stdout": cp.stdout.strip()[:500],
            "version_stderr": cp.stderr.strip()[:500],
        })
    except Exception as exc:
        row.update({"version_error": f"{type(exc).__name__}:{exc}"})
    return row


def preflight_tools(output_path: Path) -> dict[str, Any]:
    tools = [probe_tool(name) for name in REQUIRED_TOOLS]
    missing = [row["tool"] for row in tools if not row.get("found")]
    result = {
        "schema": "mb.sandbox_factory.tool_preflight.v1",
        "created_utc": utc_now(),
        "verdict": "PASS" if not missing else "BLOCKED",
        "missing_tools": missing,
        "tools": tools,
    }
    write_json(output_path, result)
    return result


def main() -> int:
    out = Path("TOOL_PREFLIGHT.json")
    result = preflight_tools(out)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

