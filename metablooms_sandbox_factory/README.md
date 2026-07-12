# MetaBlooms Sandbox Factory

Sandbox-native governed inspection and repair factory for MetaBlooms OS candidates.

The factory is designed to replace the Windows -> WSL -> Windows loop with one
workspace-native command that:

- verifies candidate SHA-256 binding
- safely extracts candidate archives
- runs the proven Stage071N V4 analyzer harness
- preserves raw analyzer evidence
- normalizes PASS / FAIL / BLOCKED verdicts
- generates focused repair worklists
- rebuilds repaired candidates with SHA sidecars
- packages return evidence for handoff

## Quick Start

In the Codex desktop workspace, use the bundled Python runtime when plain
`python` is not on `PATH`:

```powershell
$PY="C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
```

Fast preflight without running analyzers:

```powershell
& $PY metablooms_sandbox_factory/run_pipeline.py `
  --candidate outputs/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst `
  --expected-sha256 5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b `
  --allow-missing-tools `
  --preflight-only
```

Full governed analyzer run, when all eight tools are installed:

```powershell
& $PY metablooms_sandbox_factory/run_pipeline.py `
  --candidate outputs/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst `
  --expected-sha256 5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b
```

## Output

Each run writes a timestamped directory under:

```text
metablooms_sandbox_factory/runs/
```

Important files:

- `VERDICT.json`
- `FACTORY_RUN_RECEIPT.json`
- `ANALYZER_RETURN_PACKAGE.tar.gz`
- `repair/REPAIR_WORKLIST.json`
- `repair/REPAIR_WORKLIST.md`

## Verdict Semantics

- `PASS`: inspection completed and no true blockers remain
- `FAIL`: inspection completed and one or more true blockers remain
- `BLOCKED`: inspection was incomplete, untrustworthy, or missing required tools
- `PREFLIGHT_PASS`: candidate, archive, harness, and policy checks passed without
  launching analyzers

## Required Analyzer Tools

The factory fails closed unless these eight tools are visible on `PATH`:

- `ruff`
- `mypy`
- `bandit`
- `semgrep`
- `shellcheck`
- `syft`
- `trivy`
- `grype`

`--preflight-only` is the low-cost way to discover missing tools before an
expensive run. `--allow-missing-tools` is only for readiness checks; a real PASS
still requires the V4 harness to run all required analyzers successfully.

## Design Rule

The factory does not hide findings. Candidate-bound exceptions must be exact:

- candidate SHA
- tool
- path
- parser or rule type
- documented reason
