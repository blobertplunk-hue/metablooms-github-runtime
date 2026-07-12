# MetaBlooms OS GitHub Runtime

This repository kit makes the full MetaBlooms runtime runnable by GitHub-capable
agents, including ChatGPT, Codex, Claude Code, Grok, GitHub Actions, and similar
coding agents.

The runtime archive is intentionally not assumed to be a normal Git blob. The
repo stores the bootstrap, manifest, policy, agent contracts, and verification
logic. The large OS archive should be supplied as a GitHub Release asset, Git LFS
artifact, or environment-provided URL.

## Runtime Archive

Current clean runtime:

```text
METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst
```

Required SHA-256:

```text
5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b
```

Preferred GitHub release tag:

```text
metablooms-os-r5
```

## Agent Quick Start

Verify the runtime archive:

```bash
python3 scripts/metablooms_runtime.py --verify-only
```

Extract the runtime:

```bash
python3 scripts/metablooms_runtime.py --extract
```

Run the safe boot probe:

```bash
python3 scripts/metablooms_runtime.py --boot
```

Run the full boot path:

```bash
python3 scripts/metablooms_runtime.py --full-boot
```

If the archive is not present locally, set:

```bash
export METABLOOMS_RUNTIME_URL="https://github.com/OWNER/REPO/releases/download/metablooms-os-r5/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst"
```

## Windows

```powershell
.\scripts\metablooms-runtime.ps1 -Boot
```

## Governed Inspection

Use the sandbox factory to run or preflight the V4 inspection:

```bash
python3 metablooms_sandbox_factory/run_pipeline.py \
  --candidate artifacts/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst \
  --expected-sha256 5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b
```

The inspection factory fails closed when required analyzer tools are missing.

## Shared Agent Contract

All agents should read `AGENTS.md` first.

## External SARP Through GitHub

Use GitHub issues for ChatGPT UI SARP review:

1. Create an issue with the `External SARP Review` template.
2. Put the bounded question, manifest, and evidence links in the issue.
3. Ask ChatGPT to open the issue through the GitHub connector.
4. ChatGPT replies using `docs/SARP_VERDICT_TEMPLATE.md`.
5. Validate any saved verdict with:

```bash
python3 scripts/sarp_connector.py validate-verdict --file PATH_TO_VERDICT.md
```

SARP verdicts are review evidence only. They do not authorize implementation,
promotion, GitHub writes, merges, operator push, publication, or rollout.

You can also dispatch a SARP issue to a different agent through GitHub Actions:

```text
Actions -> SARP Agent Review
```

See `docs/SARP_AGENT_ACTIONS_BRIDGE.md`.

For free replies, run that workflow with provider `free`. This posts a no-cost
SARP intake response. It does not call paid APIs or grant semantic approval.

For multi-agent back-and-forth, use:

```text
docs/SARP_MULTI_AGENT_CONVERGENCE_WORKFLOW.md
```

Each agent posts an attack verdict. ChatGPT MetaBlooms synthesizes the attacks
into a revised SARP packet and repeats until convergence.
