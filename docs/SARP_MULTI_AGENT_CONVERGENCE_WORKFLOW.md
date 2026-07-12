# Multi-Agent SARP Convergence Workflow

This workflow runs SARP as a repeated adversarial review loop.

## Goal

A group of agents attack the same SARP packet, each returns structured findings,
and ChatGPT MetaBlooms synthesizes their critiques into a revised packet. The
loop repeats until convergence.

## Round Shape

1. Open a GitHub issue from `External SARP Review`.
2. Add label `sarp-round`.
3. Ask each agent to reply with `docs/SARP_AGENT_ATTACK_TEMPLATE.md`.
4. Save or copy the replies into a round folder:

```text
sarp/rounds/<round_id>/verdicts/
```

5. Run:

```bash
python3 scripts/sarp_roundtrip.py synthesize \
  --round-dir sarp/rounds/<round_id> \
  --out sarp/rounds/<round_id>/SARP_CONVERGENCE_REPORT.md
```

6. ChatGPT MetaBlooms reviews the convergence report and prepares the next
packet revision.
7. Repeat until convergence.

## Convergence Rule

Default convergence is conservative:

- At least 3 reviewers.
- No `critical` open findings.
- No `high` open findings.
- At least 2 reviewers mark `ready_for_next_round` false because no further
  attack is needed, or verdicts are `APPROVED`/`APPROVED_WITH_CONDITIONS`.
- All authorization flags remain false.

## Roles

Suggested reviewer roles:

- `security_attacker`
- `governance_attacker`
- `evidence_attacker`
- `github_connector_attacker`
- `operator_workflow_attacker`
- `release_integrity_attacker`

## Non-Authorization Boundary

Convergence does not authorize implementation, promotion, merge, push,
publication, or rollout. It only says the review packet has converged enough to
be used as evidence for a separately authorized next step.

