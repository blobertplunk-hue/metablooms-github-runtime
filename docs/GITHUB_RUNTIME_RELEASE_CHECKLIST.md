# GitHub Runtime Release Checklist

Use this checklist when publishing the MetaBlooms runtime to GitHub.

## 1. Create the Repository

Create a GitHub repository containing the files from this kit.

Do not commit the runtime archive as an ordinary Git blob unless Git LFS is
enabled and working.

## 2. Publish the Runtime Archive

Preferred release tag:

```text
metablooms-os-r5
```

Release asset:

```text
METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst
```

Required SHA-256:

```text
5866f9754b922c77653cd0745fe27bb729902c4332b43f542221d6ba7c823c2b
```

Example with GitHub CLI:

```bash
gh release create metablooms-os-r5 \
  outputs/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst \
  outputs/METABLOOMS_OS_STAGE071N_V4_R5_REPAIRED_CANDIDATE_20260711T1518.tar.zst.sha256 \
  --title "MetaBlooms OS R5 Clean Runtime" \
  --notes "Clean R5 runtime. V4 inspection PASS. SHA-256 bound in metablooms_runtime_manifest.json."
```

## 3. Verify Through GitHub Actions

Run the workflow:

```text
MetaBlooms Runtime Verify
```

If the release asset is private or not discoverable by direct URL, run the
workflow manually and provide `runtime_url`.

## 4. Agent Handoff

Tell agents:

1. Read `AGENTS.md`.
2. Read `metablooms_runtime_manifest.json`.
3. Run `python3 scripts/metablooms_runtime.py --verify-only`.
4. Run `python3 scripts/metablooms_runtime.py --boot`.
5. Report `runtime_work/METABLOOMS_RUNTIME_RECEIPT.json`.

## 5. Fail-Closed Boundary

Any missing archive, SHA mismatch, unsafe archive member, missing boot entry, or
missing analyzer tool is a governed `BLOCKED` state, not permission to improvise.

