# SARP Through the ChatGPT GitHub Connector

This workflow lets ChatGPT UI perform External SARP review using only GitHub
connector access.

## What SARP Means Here

SARP is a bounded external review/adjudication lane. It reviews a specific
packet of evidence and returns a structured verdict.

SARP does not authorize:

- promotion
- canonical publication
- GitHub writes beyond the SARP issue/comment itself
- connector writes beyond the SARP issue/comment itself
- merges
- operator push
- hosted publication
- untrusted execution
- broader rollout

## Repository Setup

Create a GitHub issue with the `External SARP Review` issue form.

Attach or link one SARP packet. The packet should contain:

- readme
- seed
- review packet
- manifest
- evidence files
- receipts, schemas, or fixtures as needed

The packet manifest must use:

```text
mb.sarp_delivery.manifest.v1
```

## ChatGPT Connector Steps

1. Open the GitHub issue.
2. Read the issue scope and forbidden actions.
3. Read `metablooms_runtime_manifest.json` if runtime identity matters.
4. Read the SARP manifest or release asset metadata.
5. Verify the exact bounded question.
6. Decide one of:
   - `APPROVED`
   - `APPROVED_WITH_CONDITIONS`
   - `REJECTED`
   - `BLOCKED_INSUFFICIENT_EVIDENCE`
   - `CHANGES_REQUESTED`
7. Reply using `docs/SARP_VERDICT_TEMPLATE.md`.

## Connector-Safe Rule

If the ChatGPT UI cannot inspect a linked artifact or verify a SHA-256, the
verdict must be `BLOCKED_INSUFFICIENT_EVIDENCE`.

## Required Separation

Keep External SARP files and implementation files visibly separate.

The SARP issue may link to implementation candidates as evidence, but the
verdict must not say that review approval authorizes implementation, promotion,
merge, push, or publication.

## After Verdict

An implementation agent may use the verdict as evidence, but material OS changes
still need:

1. converged SARP verdict
2. explicit user authorization
3. pre/post validation
4. receipt-bound artifact identity checks

## Optional: Different Agent Through Actions

Use `.github/workflows/sarp-agent-review.yml` to dispatch the SARP issue to a
different agent provider and post its verdict back to the issue. See
`docs/SARP_AGENT_ACTIONS_BRIDGE.md`.

## Optional: Multi-Agent Convergence

Use `.github/ISSUE_TEMPLATE/sarp-convergence-round.yml` and
`docs/SARP_MULTI_AGENT_CONVERGENCE_WORKFLOW.md` when several agents should
attack the same packet. ChatGPT MetaBlooms should synthesize their findings into
a revised packet and repeat until convergence.
