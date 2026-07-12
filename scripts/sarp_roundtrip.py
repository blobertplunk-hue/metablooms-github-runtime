from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
TERMINAL_POSITIVE = {"APPROVED", "APPROVED_WITH_CONDITIONS"}
FALSE_FLAGS = ("implementation_authorized", "promotion_authorized", "github_write_authorized", "merge_authorized")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    raw = fenced.group(1) if fenced else text
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    return json.loads(raw[start : end + 1])


def load_attack_file(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    try:
        obj = extract_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [{"code": "ATTACK_PARSE_ERROR", "path": str(path), "detail": f"{type(exc).__name__}:{exc}"}]
    if obj.get("schema") != "mb.sarp.agent_attack.v1":
        errors.append({"code": "BAD_SCHEMA", "path": str(path), "actual": obj.get("schema")})
    for key in ("round_id", "agent", "packet", "verdict", "findings", "required_improvements"):
        if key not in obj:
            errors.append({"code": "REQUIRED_FIELD_MISSING", "path": str(path), "field": key})
    for key in FALSE_FLAGS:
        if obj.get(key) is not False:
            errors.append({"code": "AUTHORIZATION_FLAG_MUST_BE_FALSE", "path": str(path), "field": key, "actual": obj.get(key)})
    return obj, errors


def collect_attacks(round_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    verdict_dir = round_dir / "verdicts"
    attacks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in sorted(verdict_dir.glob("*")):
        if path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        obj, path_errors = load_attack_file(path)
        errors.extend(path_errors)
        if obj is not None:
            obj["_source_path"] = str(path)
            obj["_source_sha256"] = sha256_file(path)
            attacks.append(obj)
    return attacks, errors


def summarize(round_dir: Path) -> dict[str, Any]:
    attacks, errors = collect_attacks(round_dir)
    verdicts = Counter(a.get("verdict") for a in attacks)
    roles = Counter((a.get("agent") or {}).get("role") for a in attacks)
    open_by_severity: Counter[str] = Counter()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    required: list[dict[str, Any]] = []
    for attack in attacks:
        agent = attack.get("agent") or {}
        for finding in attack.get("findings") or []:
            severity = finding.get("severity", "info")
            status = finding.get("status", "open")
            if status == "open":
                open_by_severity[severity] += 1
            key = finding.get("claim") or finding.get("suggested_improvement") or finding.get("id")
            grouped[str(key)].append({
                "agent": agent.get("name"),
                "role": agent.get("role"),
                "severity": severity,
                "status": status,
                "suggested_improvement": finding.get("suggested_improvement"),
                "evidence": finding.get("evidence"),
            })
        for item in attack.get("required_improvements") or []:
            required.append({"agent": agent.get("name"), "role": agent.get("role"), "improvement": item})

    reviewer_count = len({(a.get("agent") or {}).get("name") for a in attacks if (a.get("agent") or {}).get("name")})
    blocking = open_by_severity.get("critical", 0) + open_by_severity.get("high", 0)
    positive = sum(verdicts.get(v, 0) for v in TERMINAL_POSITIVE)
    convergence = "CONVERGED" if reviewer_count >= 3 and blocking == 0 and positive >= 2 and not errors else "CONTINUE"
    if errors:
        convergence = "BLOCKED_INVALID_ROUND"
    return {
        "schema": "mb.sarp.convergence_round_report.v1",
        "round_dir": str(round_dir),
        "reviewer_count": reviewer_count,
        "attack_count": len(attacks),
        "verdict_counts": dict(verdicts),
        "role_counts": dict(roles),
        "open_findings_by_severity": dict(open_by_severity),
        "blocking_open_findings": blocking,
        "required_improvements": required,
        "grouped_findings": grouped,
        "validation_errors": errors,
        "convergence_decision": convergence,
        "non_authorization_boundary": {
            "implementation_authorized": False,
            "promotion_authorized": False,
            "github_write_authorized": False,
            "merge_authorized": False,
        },
    }


def write_markdown(report: dict[str, Any], out: Path) -> None:
    lines = [
        "# SARP Multi-Agent Convergence Report",
        "",
        f"Decision: **{report['convergence_decision']}**",
        "",
        f"- Reviewers: {report['reviewer_count']}",
        f"- Attack files: {report['attack_count']}",
        f"- Blocking open findings: {report['blocking_open_findings']}",
        f"- Verdict counts: `{json.dumps(report['verdict_counts'], sort_keys=True)}`",
        f"- Open findings by severity: `{json.dumps(report['open_findings_by_severity'], sort_keys=True)}`",
        "",
        "## Required Improvements",
        "",
    ]
    if report["required_improvements"]:
        for item in report["required_improvements"]:
            lines.append(f"- **{item.get('agent')} / {item.get('role')}**: {item.get('improvement')}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Grouped Findings", ""])
    grouped = report["grouped_findings"]
    if grouped:
        for claim, entries in grouped.items():
            worst = sorted((e.get("severity", "info") for e in entries), key=lambda x: SEVERITY_ORDER.get(x, 99))[0]
            lines.append(f"### {claim}")
            lines.append("")
            lines.append(f"Worst severity: `{worst}`")
            lines.append("")
            for entry in entries:
                lines.append(f"- `{entry.get('agent')}` / `{entry.get('role')}` / `{entry.get('severity')}` / `{entry.get('status')}`: {entry.get('suggested_improvement')}")
            lines.append("")
    else:
        lines.append("- None recorded.")
    lines.extend([
        "## Non-Authorization Boundary",
        "",
        "This convergence report does not authorize implementation, promotion, GitHub writes, merge, push, publication, or rollout.",
        "",
    ])
    if report["validation_errors"]:
        lines.extend(["## Validation Errors", ""])
        for error in report["validation_errors"]:
            lines.append(f"- `{error.get('code')}`: `{json.dumps(error, sort_keys=True)}`")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def init_round(args: argparse.Namespace) -> int:
    round_dir = Path(args.round_dir)
    (round_dir / "verdicts").mkdir(parents=True, exist_ok=True)
    seed = {
        "schema": "mb.sarp.convergence_round.v1",
        "round_id": args.round_id,
        "packet": args.packet,
        "bounded_question": args.bounded_question,
        "agents_requested": args.agents.split(",") if args.agents else [],
        "non_authorization_boundary": {
            "implementation_authorized": False,
            "promotion_authorized": False,
            "github_write_authorized": False,
            "merge_authorized": False,
        },
    }
    write_json(round_dir / "ROUND.json", seed)
    return 0


def synthesize(args: argparse.Namespace) -> int:
    report = summarize(Path(args.round_dir))
    write_json(Path(args.round_dir) / "SARP_CONVERGENCE_REPORT.json", report)
    write_markdown(report, Path(args.out))
    print(json.dumps({
        "decision": report["convergence_decision"],
        "reviewers": report["reviewer_count"],
        "blocking_open_findings": report["blocking_open_findings"],
        "out": args.out,
    }, indent=2, sort_keys=True))
    return 0 if report["convergence_decision"] == "CONVERGED" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run multi-agent SARP convergence rounds.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-round")
    init.add_argument("--round-dir", required=True)
    init.add_argument("--round-id", required=True)
    init.add_argument("--packet", required=True)
    init.add_argument("--bounded-question", required=True)
    init.add_argument("--agents", default="security_attacker,governance_attacker,evidence_attacker,github_connector_attacker")
    synth = sub.add_parser("synthesize")
    synth.add_argument("--round-dir", required=True)
    synth.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "init-round":
        return init_round(args)
    if args.command == "synthesize":
        return synthesize(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
