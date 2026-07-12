## External SARP Verdict

```json
{
  "schema": "mb.github_connector.sarp_verdict.v1",
  "verdict": "APPROVED",
  "reviewer": "ChatGPT GitHub connector",
  "packet": {
    "manifest_path_or_url": "",
    "primary_archive_or_issue": "",
    "sha256_verified": false
  },
  "bounded_question": "",
  "decision_summary": "",
  "findings": [],
  "conditions": [],
  "blocked_actions": [
    "promotion",
    "canonical_publication",
    "github_write_except_this_verdict",
    "connector_write_except_this_verdict",
    "merge",
    "operator_push",
    "hosted_publication",
    "untrusted_execution",
    "broader_rollout"
  ],
  "implementation_authorized": false,
  "promotion_authorized": false,
  "github_write_authorized": false,
  "merge_authorized": false,
  "next_allowed_action": "Use this verdict as review evidence only; seek explicit user authorization before any material OS implementation or promotion."
}
```

