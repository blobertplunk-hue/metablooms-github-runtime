#!/usr/bin/env python3
"""Validate downstream receipt identity against one frozen release subject."""
from __future__ import annotations

from typing import Any


def _subject_errors(subject: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifact_sha = subject.get("artifact_sha256")
    if not isinstance(artifact_sha, str) or len(artifact_sha) != 64:
        errors.append("SUBJECT_INVALID_ARTIFACT_SHA256")
    generation = subject.get("contract_generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        errors.append("SUBJECT_INVALID_CONTRACT_GENERATION")
    return errors


def validate_binding(receipts: list[dict], subject: dict) -> list[str]:
    """Return deterministic identity errors; empty means every receipt binds.

    Task-1 binding is intentionally narrow: every dynamic receipt must carry
    the exact ``artifact_sha256`` and ``contract_generation`` of the frozen
    subject. Later gates may require additional evidence fields.
    """
    errors = _subject_errors(subject)
    if not isinstance(receipts, list):
        return errors + ["RECEIPTS_NOT_LIST"]

    expected_sha = subject.get("artifact_sha256")
    expected_generation = subject.get("contract_generation")
    for index, receipt in enumerate(receipts):
        prefix = f"receipt[{index}]"
        if not isinstance(receipt, dict):
            errors.append(f"{prefix}:RECEIPT_NOT_OBJECT")
            continue

        if "artifact_sha256" not in receipt:
            errors.append(f"{prefix}:MISSING_ARTIFACT_SHA256")
        elif receipt.get("artifact_sha256") != expected_sha:
            errors.append(f"{prefix}:ARTIFACT_SHA256_MISMATCH")

        if "contract_generation" not in receipt:
            errors.append(f"{prefix}:MISSING_CONTRACT_GENERATION")
        elif receipt.get("contract_generation") != expected_generation:
            errors.append(f"{prefix}:CONTRACT_GENERATION_MISMATCH")

    return errors


def _matrix_leg_spec(raw: str) -> dict[str, str] | None:
    """Return the exact runtime family/version expected by one declared leg."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    lower = text.lower()
    if lower.startswith("windows powershell "):
        version = text[len("Windows PowerShell "):].strip()
        if not version:
            return None
        return {
            "declared_matrix_leg": text,
            "runtime_name": "powershell.exe",
            "powershell_edition": "Desktop",
            "powershell_version": version,
        }
    if lower.startswith("powershell "):
        version = text[len("PowerShell "):].strip()
        if not version:
            return None
        return {
            "declared_matrix_leg": text,
            "runtime_name": "pwsh.exe",
            "powershell_edition": "Core",
            "powershell_version": version,
        }
    if all(part.isdigit() for part in text.split(".")):
        return {
            "declared_matrix_leg": text,
            "runtime_name": "pwsh.exe",
            "powershell_edition": "Core",
            "powershell_version": text,
        }
    return None


def _version_matches(expected: str, observed: Any) -> bool:
    if not isinstance(observed, str) or not observed.strip():
        return False
    observed_text = observed.strip()
    if expected == "5.1":
        return observed_text == "5.1" or observed_text.startswith("5.1.")
    return observed_text == expected


def _runtime_matches(spec: dict[str, str], execution: dict[str, Any]) -> bool:
    path = execution.get("selected_runtime_path")
    if not isinstance(path, str) or not path.strip():
        return False
    normalized = path.replace("/", "\\").lower()
    runtime_name = spec["runtime_name"].lower()
    if not normalized.endswith("\\" + runtime_name) and normalized != runtime_name:
        return False
    if execution.get("powershell_edition") != spec["powershell_edition"]:
        return False
    return _version_matches(spec["powershell_version"], execution.get("powershell_version"))


def validate_hosted_windows_evidence(subject: dict, hosted_receipt: dict) -> dict[str, Any]:
    """Validate H2 hosted-Windows execution evidence for one frozen subject."""
    failure_classes: list[str] = []
    missing_matrix_legs: list[str] = []

    if not isinstance(subject, dict):
        return {"decision": "BLOCKED", "failure_classes": ["SUBJECT_NOT_OBJECT"]}
    if not isinstance(hosted_receipt, dict):
        return {"decision": "GATE_INCOMPLETE", "failure_classes": ["HOSTED_RECEIPT_REQUIRED"]}

    for field, failure in (
        ("artifact_sha256", "HOSTED_ARTIFACT_SHA256_MISMATCH"),
        ("contract_sha256", "HOSTED_CONTRACT_SHA256_MISMATCH"),
        ("contract_generation", "HOSTED_CONTRACT_GENERATION_MISMATCH"),
    ):
        if hosted_receipt.get(field) != subject.get(field):
            failure_classes.append(failure)

    if hosted_receipt.get("schema") != "mb.powershell.hosted_plane_receipt.v1":
        failure_classes.append("HOSTED_RECEIPT_SCHEMA_INVALID")
    if hosted_receipt.get("phase_id") != "H2-HOSTED-WINDOWS":
        failure_classes.append("HOSTED_PHASE_ID_INVALID")

    verifier_commit = hosted_receipt.get("verifier_commit")
    if not isinstance(verifier_commit, str) or len(verifier_commit) != 40 or any(
        c not in "0123456789abcdefABCDEF" for c in verifier_commit
    ):
        failure_classes.append("VERIFIER_COMMIT_BINDING_REQUIRED")
    toolchain_lock_sha = hosted_receipt.get("toolchain_lock_sha256")
    if not isinstance(toolchain_lock_sha, str) or len(toolchain_lock_sha) != 64 or any(
        c not in "0123456789abcdefABCDEF" for c in toolchain_lock_sha
    ):
        failure_classes.append("TOOLCHAIN_LOCK_BINDING_REQUIRED")
    evidence_hashes = hosted_receipt.get("evidence_sha256")
    required_evidence = {
        "hosted_environment.json",
        "install_tree_manifest.json",
        "entrypoint_execution.json",
    }
    if not isinstance(evidence_hashes, dict) or any(
        not isinstance(evidence_hashes.get(name), str)
        or len(evidence_hashes.get(name, "")) != 64
        for name in required_evidence
    ):
        failure_classes.append("HOSTED_EVIDENCE_HASH_BINDING_REQUIRED")

    environment = hosted_receipt.get("environment")
    is_native_windows = (
        isinstance(environment, dict)
        and str(environment.get("os_family", "")).lower() == "windows"
        and environment.get("native_windows") is True
        and isinstance(environment.get("host_os"), str)
        and "windows" in environment.get("host_os", "").lower()
    )
    if not is_native_windows:
        failure_classes.append("NATIVE_WINDOWS_EVIDENCE_REQUIRED")

    entrypoints = subject.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints or any(
        not isinstance(item, str) or not item.strip() for item in entrypoints
    ):
        failure_classes.append("SUBJECT_ENTRYPOINTS_INVALID")
        entrypoints = []
    declared_entrypoints = {item.replace("/", "\\").lower() for item in entrypoints}

    matrix = subject.get("declared_powershell_matrix")
    specs: list[dict[str, str]] = []
    if not isinstance(matrix, list) or not matrix:
        failure_classes.append("SUBJECT_POWERSHELL_MATRIX_INVALID")
    else:
        for raw in matrix:
            spec = _matrix_leg_spec(raw)
            if spec is None:
                failure_classes.append("SUBJECT_POWERSHELL_MATRIX_LEG_UNSUPPORTED")
            else:
                specs.append(spec)

    executions = hosted_receipt.get("executions")
    if not isinstance(executions, list):
        executions = []
        failure_classes.append("HOSTED_EXECUTIONS_REQUIRED")

    exact_entrypoint_seen = False
    severe_execution_failure = False
    covered_legs: set[str] = set()
    for execution in executions:
        if not isinstance(execution, dict):
            severe_execution_failure = True
            failure_classes.append("HOSTED_EXECUTION_RECORD_INVALID")
            continue

        entrypoint = execution.get("entrypoint")
        normalized_entrypoint = (
            entrypoint.replace("/", "\\").lower()
            if isinstance(entrypoint, str)
            else ""
        )
        if execution.get("entrypoint_executed") is True and normalized_entrypoint in declared_entrypoints:
            exact_entrypoint_seen = True
        else:
            severe_execution_failure = True
            failure_classes.append("EXACT_DECLARED_ENTRYPOINT_NOT_EXECUTED")

        declared_leg = execution.get("declared_matrix_leg")
        matching_spec = next(
            (spec for spec in specs if spec["declared_matrix_leg"] == declared_leg),
            None,
        )
        if matching_spec is None:
            severe_execution_failure = True
            failure_classes.append("WRONG_POWERSHELL_RUNTIME_SELECTED")
            continue

        if is_native_windows and not _runtime_matches(matching_spec, execution):
            severe_execution_failure = True
            failure_classes.append("WRONG_POWERSHELL_RUNTIME_SELECTED")
            continue

        if execution.get("decision") != "PASS" or execution.get("exit_code") != 0:
            severe_execution_failure = True
            failure_classes.append("HOSTED_ENTRYPOINT_EXECUTION_FAILED")
            continue
        covered_legs.add(matching_spec["declared_matrix_leg"])

    if declared_entrypoints and not exact_entrypoint_seen:
        failure_classes.append("EXACT_DECLARED_ENTRYPOINT_NOT_EXECUTED")
        severe_execution_failure = True

    for spec in specs:
        leg = spec["declared_matrix_leg"]
        if leg not in covered_legs:
            missing_matrix_legs.append(leg)
    if missing_matrix_legs:
        failure_classes.append("DECLARED_POWERSHELL_MATRIX_LEG_UNEXECUTED")

    failure_classes = list(dict.fromkeys(failure_classes))
    result: dict[str, Any] = {
        "decision": "PASS",
        "failure_classes": failure_classes,
    }
    if missing_matrix_legs:
        result["missing_matrix_legs"] = missing_matrix_legs

    blocked_prefixes = {
        "HOSTED_ARTIFACT_SHA256_MISMATCH",
        "HOSTED_CONTRACT_SHA256_MISMATCH",
        "HOSTED_CONTRACT_GENERATION_MISMATCH",
        "HOSTED_RECEIPT_SCHEMA_INVALID",
        "HOSTED_PHASE_ID_INVALID",
        "SUBJECT_ENTRYPOINTS_INVALID",
        "SUBJECT_POWERSHELL_MATRIX_INVALID",
        "SUBJECT_POWERSHELL_MATRIX_LEG_UNSUPPORTED",
        "HOSTED_EXECUTION_RECORD_INVALID",
        "WRONG_POWERSHELL_RUNTIME_SELECTED",
        "EXACT_DECLARED_ENTRYPOINT_NOT_EXECUTED",
        "HOSTED_ENTRYPOINT_EXECUTION_FAILED",
    }
    if severe_execution_failure or any(item in blocked_prefixes for item in failure_classes):
        result["decision"] = "BLOCKED"
    elif failure_classes:
        result["decision"] = "GATE_INCOMPLETE"
    return result
