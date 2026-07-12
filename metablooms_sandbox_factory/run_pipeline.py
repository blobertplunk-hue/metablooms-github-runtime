from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metablooms_sandbox_factory.analyzers.install_or_locate_tools import preflight_tools
from metablooms_sandbox_factory.factory_common import (
    ROOT,
    RUNS,
    WORKSPACE,
    ensure_dirs,
    make_return_archive,
    path_env,
    read_json,
    relative_to_workspace,
    sha256_file,
    stamp,
    utc_now,
    write_json,
    write_sidecar,
)
from metablooms_sandbox_factory.packaging.verify_artifact import verify_archive
from metablooms_sandbox_factory.repair.blocker_worklist import build_worklist


DEFAULT_HARNESS = ROOT / "vendor" / "stage071n_v4_r5" / "stage071n_v4_analyzer_harness.py"
DEFAULT_POLICY = ROOT / "vendor" / "stage071n_v4_r5" / "V4_ANALYZER_POLICY.json"


def blocked_receipt(run_dir: Path, candidate: Path | None, code: str, detail: str) -> dict[str, Any]:
    receipt = {
        "schema": "mb.sandbox_factory.run_receipt.v1",
        "created_utc": utc_now(),
        "verdict": "BLOCKED",
        "blocker": {"code": code, "detail": detail},
        "candidate": str(candidate) if candidate else None,
    }
    write_json(run_dir / "FACTORY_RUN_RECEIPT.json", receipt)
    write_json(run_dir / "VERDICT.json", {
        "schema": "mb.sandbox_factory.verdict.v1",
        "verdict": "BLOCKED",
        "code": code,
        "detail": detail,
    })
    return receipt


def preflight_receipt(
    *,
    run_dir: Path,
    candidate: Path,
    actual_sha: str,
    artifact_check: dict[str, Any],
    tool_preflight: dict[str, Any],
    harness: Path,
    policy: Path,
) -> dict[str, Any]:
    missing_tools = tool_preflight.get("missing_tools", [])
    verdict = "PREFLIGHT_PASS" if artifact_check.get("verdict") == "PASS" and harness.is_file() and policy.is_file() else "BLOCKED"
    receipt = {
        "schema": "mb.sandbox_factory.run_receipt.v1",
        "created_utc": utc_now(),
        "mode": "preflight_only",
        "verdict": verdict,
        "candidate": {
            "path": str(candidate),
            "sha256": actual_sha,
        },
        "artifact_verification": artifact_check,
        "tool_preflight": {
            "verdict": tool_preflight.get("verdict"),
            "missing_tools": missing_tools,
            "allowed_to_continue": bool(missing_tools),
        },
        "harness": {
            "path": str(harness),
            "exists": harness.is_file(),
        },
        "policy": {
            "path": str(policy),
            "exists": policy.is_file(),
        },
    }
    write_json(run_dir / "FACTORY_RUN_RECEIPT.json", receipt)
    write_json(run_dir / "VERDICT.json", {
        "schema": "mb.sandbox_factory.verdict.v1",
        "verdict": verdict,
        "missing_tools": missing_tools,
    })
    write_sidecar(run_dir / "FACTORY_RUN_RECEIPT.json")
    return receipt


def copy_if_exists(src: Path, dst: Path) -> bool:
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def run_harness(
    *,
    harness: Path,
    candidate: Path,
    expected_sha256: str,
    policy: Path,
    analyzer_return: Path,
    run_dir: Path,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(harness),
        "run",
        "--candidate",
        str(candidate),
        "--expected-sha256",
        expected_sha256,
        "--policy",
        str(policy),
        "--output-dir",
        str(analyzer_return),
    ]
    meta = {
        "schema": "mb.sandbox_factory.harness_invocation.v1",
        "command": cmd,
        "harness": str(harness),
        "candidate": str(candidate),
        "policy": str(policy),
        "started_utc": utc_now(),
    }
    cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=14400, env=path_env())
    meta.update({
        "finished_utc": utc_now(),
        "exit_code": cp.returncode,
        "stdout_tail": cp.stdout[-4000:],
        "stderr_tail": cp.stderr[-4000:],
    })
    write_json(run_dir / "HARNESS_INVOCATION.json", meta)
    (run_dir / "HARNESS_STDOUT.txt").write_text(cp.stdout, encoding="utf-8", errors="replace")
    (run_dir / "HARNESS_STDERR.txt").write_text(cp.stderr, encoding="utf-8", errors="replace")
    return meta


def collect_results(analyzer_return: Path, run_dir: Path) -> dict[str, Any]:
    normalized = analyzer_return / "normalized"
    verdict_path = normalized / "V4_VERDICT.json"
    if not verdict_path.is_file():
        verdict_path = analyzer_return / "V4_VERDICT.json"
    if verdict_path.is_file():
        verdict = read_json(verdict_path)
    else:
        verdict = {
            "schema": "mb.stage071n.v4.verdict.v1",
            "verdict": "BLOCKED",
            "coverage_gap_count": 1,
            "gaps": [{"code": "missing_v4_verdict"}],
        }
    write_json(run_dir / "VERDICT.json", verdict)
    copy_if_exists(normalized / "BLOCKERS.json", run_dir / "normalized" / "BLOCKERS.json")
    copy_if_exists(normalized / "COVERAGE_GAPS.json", run_dir / "normalized" / "COVERAGE_GAPS.json")
    copy_if_exists(normalized / "PARSER_EXCEPTIONS.json", run_dir / "normalized" / "PARSER_EXCEPTIONS.json")
    copy_if_exists(normalized / "ROOT_CAUSE_CLUSTERS.json", run_dir / "normalized" / "ROOT_CAUSE_CLUSTERS.json")
    copy_if_exists(normalized / "NORMALIZED_FINDINGS.json", run_dir / "normalized" / "NORMALIZED_FINDINGS.json")
    return verdict


def pipeline(args: argparse.Namespace) -> int:
    ensure_dirs()
    candidate = Path(args.candidate).resolve()
    run_dir = RUNS / f"{stamp()}_{candidate.stem[:48]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if not candidate.is_file():
        blocked_receipt(run_dir, candidate, "candidate_missing", str(candidate))
        print(f"BLOCKED candidate missing: {candidate}")
        return 2

    actual_sha = sha256_file(candidate)
    if args.expected_sha256 and actual_sha.lower() != args.expected_sha256.lower():
        blocked_receipt(run_dir, candidate, "candidate_sha_mismatch", f"expected {args.expected_sha256} got {actual_sha}")
        print(f"BLOCKED candidate SHA mismatch: {actual_sha}")
        return 2

    artifact_check = verify_archive(candidate, args.expected_sha256 or actual_sha, run_dir / "CANDIDATE_ARTIFACT_VERIFICATION.json")
    if artifact_check["verdict"] != "PASS" and not args.allow_external_tar_validation:
        blocked_receipt(run_dir, candidate, "candidate_archive_validation_failed", json.dumps(artifact_check.get("errors") or []))
        print("BLOCKED candidate archive validation failed")
        return 2

    tool_preflight = preflight_tools(run_dir / "TOOL_PREFLIGHT.json")
    if tool_preflight["verdict"] != "PASS" and not args.allow_missing_tools:
        blocked_receipt(run_dir, candidate, "required_tools_missing", ",".join(tool_preflight["missing_tools"]))
        print(f"BLOCKED missing tools: {', '.join(tool_preflight['missing_tools'])}")
        return 2

    harness = Path(args.harness).resolve()
    policy = Path(args.policy).resolve()
    if not harness.is_file():
        blocked_receipt(run_dir, candidate, "harness_missing", str(harness))
        print(f"BLOCKED harness missing: {harness}")
        return 2
    if not policy.is_file():
        blocked_receipt(run_dir, candidate, "policy_missing", str(policy))
        print(f"BLOCKED policy missing: {policy}")
        return 2

    if args.preflight_only:
        receipt = preflight_receipt(
            run_dir=run_dir,
            candidate=candidate,
            actual_sha=actual_sha,
            artifact_check=artifact_check,
            tool_preflight=tool_preflight,
            harness=harness,
            policy=policy,
        )
        print(json.dumps({
            "verdict": receipt["verdict"],
            "run_dir": relative_to_workspace(run_dir),
            "candidate_sha256": actual_sha,
            "missing_tools": tool_preflight.get("missing_tools", []),
        }, indent=2, sort_keys=True))
        return 0 if receipt["verdict"] == "PREFLIGHT_PASS" else 2

    analyzer_return = run_dir / "ANALYZER_RETURN"
    invocation = run_harness(
        harness=harness,
        candidate=candidate,
        expected_sha256=args.expected_sha256 or actual_sha,
        policy=policy,
        analyzer_return=analyzer_return,
        run_dir=run_dir,
    )
    verdict = collect_results(analyzer_return, run_dir)

    blockers_path = analyzer_return / "normalized" / "BLOCKERS.json"
    if blockers_path.is_file():
        build_worklist(blockers_path, run_dir / "repair")

    return_archive = make_return_archive(analyzer_return, run_dir / "ANALYZER_RETURN_PACKAGE.tar.gz") if analyzer_return.exists() else None
    receipt = {
        "schema": "mb.sandbox_factory.run_receipt.v1",
        "created_utc": utc_now(),
        "candidate": {
            "path": str(candidate),
            "sha256": actual_sha,
        },
        "harness": str(harness),
        "policy": str(policy),
        "run_dir": str(run_dir),
        "verdict": verdict.get("verdict"),
        "v4_verdict": verdict,
        "tool_preflight": {
            "verdict": tool_preflight["verdict"],
            "missing_tools": tool_preflight["missing_tools"],
        },
        "harness_exit_code": invocation.get("exit_code"),
        "return_archive": str(return_archive) if return_archive else None,
        "return_archive_sha256": sha256_file(return_archive) if return_archive else None,
    }
    write_json(run_dir / "FACTORY_RUN_RECEIPT.json", receipt)
    write_sidecar(run_dir / "FACTORY_RUN_RECEIPT.json")

    print(json.dumps({
        "verdict": receipt["verdict"],
        "run_dir": relative_to_workspace(run_dir),
        "candidate_sha256": actual_sha,
        "return_archive": relative_to_workspace(return_archive) if return_archive else None,
    }, indent=2, sort_keys=True))
    return 0 if verdict.get("verdict") == "PASS" else (1 if verdict.get("verdict") == "FAIL" else 2)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the MetaBlooms sandbox-native governed inspection pipeline.")
    p.add_argument("--candidate", required=True)
    p.add_argument("--expected-sha256")
    p.add_argument("--harness", default=str(DEFAULT_HARNESS))
    p.add_argument("--policy", default=str(DEFAULT_POLICY))
    p.add_argument("--allow-missing-tools", action="store_true", help="Continue into harness even if factory tool preflight finds missing tools.")
    p.add_argument("--allow-external-tar-validation", action="store_true", help="Continue if Python tar validation cannot inspect the archive.")
    p.add_argument("--preflight-only", action="store_true", help="Verify candidate, archive safety, tool readiness, harness, and policy without running analyzers.")
    return p


def main(argv: list[str] | None = None) -> int:
    return pipeline(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
