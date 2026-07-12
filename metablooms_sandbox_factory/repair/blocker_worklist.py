from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from metablooms_sandbox_factory.factory_common import read_json, utc_now, write_json


SYMBOL_RE = re.compile(r"[`\"“]([^`\"”]+)[`\"”]")


def extract_symbol(message: str) -> str | None:
    match = SYMBOL_RE.search(message or "")
    return match.group(1) if match else None


def build_worklist(blockers_path: Path, output_dir: Path) -> dict[str, Any]:
    blockers = read_json(blockers_path) if blockers_path.is_file() else []
    by_category = Counter(row.get("root_cause_category") or "unknown" for row in blockers)
    by_tool = Counter(row.get("tool") or "unknown" for row in blockers)
    by_symbol = Counter()
    files: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in blockers:
        symbol = extract_symbol(str(row.get("message") or ""))
        if symbol:
            by_symbol[symbol] += 1
        files[str(row.get("path") or "<no-path>")].append({
            "tool": row.get("tool"),
            "rule_id": row.get("rule_id"),
            "line": row.get("line"),
            "category": row.get("root_cause_category"),
            "message": row.get("message"),
        })
    shared_repairs = []
    for symbol, count in by_symbol.most_common():
        if count >= 2:
            shared_repairs.append({
                "symbol": symbol,
                "finding_count": count,
                "suggestion": f"Repair missing or conflicting binding for {symbol!r} across affected files.",
            })
    worklist = {
        "schema": "mb.sandbox_factory.repair_worklist.v1",
        "created_utc": utc_now(),
        "blocker_count": len(blockers),
        "category_counts": dict(by_category),
        "tool_counts": dict(by_tool),
        "symbol_counts": dict(by_symbol),
        "shared_repair_candidates": shared_repairs,
        "files": dict(sorted(files.items())),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "REPAIR_WORKLIST.json", worklist)
    write_markdown(output_dir / "REPAIR_WORKLIST.md", worklist)
    return worklist


def write_markdown(path: Path, worklist: dict[str, Any]) -> None:
    lines = [
        "# Repair Worklist",
        "",
        f"Blockers: `{worklist['blocker_count']}`",
        "",
        "## Categories",
        "",
    ]
    for name, count in sorted(worklist["category_counts"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Shared Repair Candidates", ""])
    for row in worklist["shared_repair_candidates"]:
        lines.append(f"- `{row['symbol']}`: `{row['finding_count']}` findings. {row['suggestion']}")
    lines.extend(["", "## Files", ""])
    for file, rows in worklist["files"].items():
        lines.append(f"- `{file}`: `{len(rows)}` blocker findings")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--blockers", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    worklist = build_worklist(Path(args.blockers), Path(args.output_dir))
    print(json.dumps({"blocker_count": worklist["blocker_count"], "files": len(worklist["files"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

