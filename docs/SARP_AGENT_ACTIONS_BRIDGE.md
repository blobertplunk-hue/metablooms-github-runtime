# SARP Agent Review Through GitHub Actions

GitHub can coordinate SARP review by dispatching a SARP issue to a selected
agent provider, then posting a bounded SARP verdict back to the issue.

## Supported Provider Slots

The workflow supports:

- `free` for a no-cost GitHub Actions intake reply with no external model call
- `stub` for dry-run testing with no external model call
- `openai` using `OPENAI_API_KEY`
- `anthropic` using `ANTHROPIC_API_KEY`
- `xai` using `XAI_API_KEY`

Repository variables can override default model names:

- `OPENAI_MODEL`
- `ANTHROPIC_MODEL`
- `XAI_MODEL`

## Workflow

Run:

```text
Actions -> SARP Agent Review -> Run workflow
```

Inputs:

- `issue_number`: the GitHub issue created from the External SARP Review template
- `provider`: `stub`, `openai`, `anthropic`, or `xai`
- `provider`: `free`, `stub`, `openai`, `anthropic`, or `xai`
- `post_comment`: whether the action should post the verdict back to the issue

## Free Replies

Use provider `free` when you want no paid API calls.

Free mode posts a deterministic SARP intake reply. It can confirm that the SARP
lane remained bounded and that no implementation/promotion authority is being
granted. It does not perform semantic external adjudication of the packet.

For no-cost substantive review, use the ChatGPT UI manually through the GitHub
connector and have ChatGPT post the verdict template as an issue comment.

## Permissions

The workflow uses:

```yaml
permissions:
  contents: read
  issues: write
```

That means the agent can read repository files and post an issue comment. It
does not receive permission to push commits, merge PRs, or publish releases.

## Safety Boundary

The bridge forces these verdict fields to `false`:

- `implementation_authorized`
- `promotion_authorized`
- `github_write_authorized`
- `merge_authorized`

The generated verdict is also validated by `scripts/sarp_connector.py`.

## Recommended Use In ChatGPT UI

1. Create or open a SARP issue.
2. Ask ChatGPT to trigger or inspect the `SARP Agent Review` workflow.
3. Choose `free` first for a no-cost reply.
4. Choose a paid provider only when you explicitly want external model review.
5. Read the posted verdict comment.

The posted verdict remains review evidence only.
