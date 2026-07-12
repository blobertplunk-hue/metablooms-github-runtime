## SARP Agent Attack Verdict

```json
{
  "schema": "mb.sarp.agent_attack.v1",
  "round_id": "",
  "agent": {
    "name": "",
    "role": "security_attacker",
    "surface": "ChatGPT UI / GitHub connector / Claude Code / Codex / Grok / human"
  },
  "packet": {
    "manifest_path_or_url": "",
    "primary_archive_or_issue": "",
    "sha256_verified": false
  },
  "verdict": "CHANGES_REQUESTED",
  "attack_summary": "",
  "findings": [
    {
      "id": "F1",
      "severity": "high",
      "status": "open",
      "claim": "",
      "evidence": "",
      "suggested_improvement": ""
    }
  ],
  "required_improvements": [],
  "nice_to_have_improvements": [],
  "ready_for_next_round": true,
  "blocked_actions": [
    "implementation",
    "promotion",
    "canonical_publication",
    "github_write_except_sarp_comments",
    "connector_write_except_sarp_comments",
    "merge",
    "operator_push",
    "hosted_publication",
    "untrusted_execution",
    "broader_rollout"
  ],
  "implementation_authorized": false,
  "promotion_authorized": false,
  "github_write_authorized": false,
  "merge_authorized": false
}
```

