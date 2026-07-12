# Claude Code Instructions

Follow `AGENTS.md` exactly. Start with `metablooms_runtime_manifest.json`,
verify the runtime archive SHA-256, then use `scripts/metablooms_runtime.py`.

Do not treat missing release assets, missing analyzer tools, or archive
validation errors as implementation failures. They are governed `BLOCKED`
states and must be reported plainly.
