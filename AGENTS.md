# MetaBlooms Runtime Agent Contract

This repository is designed for GitHub-capable agents: ChatGPT, Codex, Claude
Code, Grok, GitHub Actions, and other coding agents that can read or clone a
repository.

## First Action

Read `metablooms_runtime_manifest.json`.

## Codex Autoboot MPP

When a user asks to boot, continue, inspect, or operate MetaBlooms from this
repository, follow this Multi-Phase Protocol before making changes:

1. Research: read `AGENTS.md`, `metablooms_runtime_manifest.json`, and the
   relevant task document. Confirm repository, branch, release tag, archive
   filename, SHA-256, and current working directory.
2. Plan: state the exact boot or inspection path, including what will be
   verified and what will be considered `BLOCKED`.
3. Preflight: verify the runtime archive source is available, verify SHA-256,
   verify safe archive structure, and verify required local tools before
   running deeper work.
4. Boot: run `python3 scripts/metablooms_runtime.py --boot` unless the user
   explicitly asks for `--verify-only`, `--extract`, or `--full-boot`.
5. Receipt: report `runtime_work/METABLOOMS_RUNTIME_RECEIPT.json`, the archive
   SHA-256, and the boot verdict. Do not infer success without the receipt.

Fail closed. Missing assets, credential problems, wrong directories, SHA
mismatches, unsafe archive members, missing tools, parser errors, or incomplete
receipts are `BLOCKED`, not permission to guess.

## Runtime Artifact

The full MetaBlooms runtime archive is large and should be supplied as one of:

1. a GitHub Release asset for tag `metablooms-os-r5`
2. a Git LFS artifact under `artifacts/`
3. an environment URL in `METABLOOMS_RUNTIME_URL`
4. the local fallback under `outputs/` when working in this Codex workspace

Never trust an archive by filename. Verify SHA-256:

`5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b`

## Standard Commands

Verify only:

```bash
python3 scripts/metablooms_runtime.py --verify-only
```

Extract:

```bash
python3 scripts/metablooms_runtime.py --extract
```

Safe boot probe:

```bash
python3 scripts/metablooms_runtime.py --boot
```

Full boot:

```bash
python3 scripts/metablooms_runtime.py --full-boot
```

## Fail-Closed Rules

- If the archive is missing, report `BLOCKED`.
- If SHA-256 differs, report `BLOCKED`.
- If extraction has absolute paths, parent traversal, or links, report `BLOCKED`.
- If `Metablooms_OS/boot.py` is missing, report `BLOCKED`.
- Do not invent boot state from memory.

## Inspection

Use the sandbox factory for governed V4 inspection:

```bash
python3 metablooms_sandbox_factory/run_pipeline.py \
  --candidate artifacts/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst \
  --expected-sha256 5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b
```

## External SARP Through GitHub

For SARP work, read `docs/SARP_GITHUB_CONNECTOR_WORKFLOW.md`.

SARP is an external review lane, not an implementation lane. A SARP verdict may
approve, reject, or request changes for a bounded evidence packet. It does not
authorize promotion, canonical publication, GitHub writes, connector writes,
merges, operator push, hosted publication, untrusted execution, or broader
rollout unless a separate explicit authorization says so.

When using the ChatGPT GitHub connector:

1. Open the SARP issue created from `.github/ISSUE_TEMPLATE/sarp-review.yml`.
2. Read the packet manifest and linked evidence.
3. Verify the requested scope and forbidden actions.
4. Reply using `docs/SARP_VERDICT_TEMPLATE.md`.
5. Keep implementation links out of the External SARP section.

If a different reviewer agent is needed, use the `SARP Agent Review` GitHub
Actions workflow. It may post only a SARP verdict comment and must not receive
push, merge, promotion, or publication authority.

Use provider `free` for no-cost GitHub Actions replies. Free mode is structural
intake only; substantive approval still needs a human reviewer or ChatGPT UI
connector review.

For multi-agent convergence, use `docs/SARP_MULTI_AGENT_CONVERGENCE_WORKFLOW.md`.
Agents must post `mb.sarp.agent_attack.v1` attack verdicts. ChatGPT MetaBlooms
then synthesizes the next packet revision. Convergence remains evidence only and
does not authorize implementation or promotion.
