# Codex MetaBlooms Autoboot Prompt

Use this prompt when starting a new Codex task against the GitHub repository.

```text
Open https://github.com/blobertplunk-hue/metablooms-github-runtime and boot MetaBlooms using the repository contract.

Use MPP: research first, then plan, preflight, boot, and receipt. Read AGENTS.md and metablooms_runtime_manifest.json before taking action. Verify the GitHub release asset metablooms-os-r5, archive filename METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst, and SHA-256 5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b. Do not assume success. If the archive, credentials, tools, SHA, extraction safety, or boot receipt are incomplete, report BLOCKED with exact evidence. Otherwise run the safe boot probe and report runtime_work/METABLOOMS_RUNTIME_RECEIPT.json.
```

## Permanent Repo Contract

The permanent instruction lives in `AGENTS.md` under `Codex Autoboot MPP`.
GitHub-capable agents should read that file first, then execute the boot helper:

```bash
python3 scripts/metablooms_runtime.py --boot
```

## Expected Release Asset

- Repository: `blobertplunk-hue/metablooms-github-runtime`
- Release tag: `metablooms-os-r5`
- Archive: `METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst`
- SHA-256: `5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b`
