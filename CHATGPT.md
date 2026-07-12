# ChatGPT Instructions

When this repository is opened through a GitHub connector, use `AGENTS.md` as
the operating contract.

The fastest safe action is:

```bash
python3 scripts/metablooms_runtime.py --verify-only
```

If the runtime archive is not present, ask for the GitHub Release asset or a
`METABLOOMS_RUNTIME_URL` value rather than guessing.

For SARP through the ChatGPT GitHub connector, open the SARP issue, read
`docs/SARP_GITHUB_CONNECTOR_WORKFLOW.md`, and answer with
`docs/SARP_VERDICT_TEMPLATE.md`. Do not use a SARP verdict as permission to
push, merge, publish, or promote.
