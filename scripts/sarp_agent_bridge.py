from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_API = "https://api.github.com"
VERDICT_TEMPLATE = {
    "schema": "mb.github_connector.sarp_verdict.v1",
    "verdict": "BLOCKED_INSUFFICIENT_EVIDENCE",
    "reviewer": "github-actions-sarp-agent",
    "packet": {
        "manifest_path_or_url": "",
        "primary_archive_or_issue": "",
        "sha256_verified": False,
    },
    "bounded_question": "",
    "decision_summary": "No external agent response was produced.",
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
        "broader_rollout",
    ],
    "implementation_authorized": False,
    "promotion_authorized": False,
    "github_write_authorized": False,
    "merge_authorized": False,
    "next_allowed_action": "Use this verdict as review evidence only; seek explicit user authorization before any material OS implementation or promotion.",
}


def http_json(method: str, url: str, token: str | None, payload: Any | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "metablooms-sarp-agent-bridge",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def fetch_issue(owner: str, repo: str, issue_number: int, token: str) -> dict[str, Any]:
    return http_json("GET", f"{REPO_API}/repos/{owner}/{repo}/issues/{issue_number}", token)


def post_issue_comment(owner: str, repo: str, issue_number: int, token: str, body: str) -> None:
    http_json("POST", f"{REPO_API}/repos/{owner}/{repo}/issues/{issue_number}/comments", token, {"body": body})


def extract_field(issue_body: str, label: str) -> str:
    pattern = rf"###\s+{re.escape(label)}\s*(.*?)(?=\n###\s+|\Z)"
    match = re.search(pattern, issue_body, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def build_review_prompt(issue: dict[str, Any]) -> str:
    body = issue.get("body") or ""
    bounded_question = extract_field(body, "Bounded question")
    manifest = extract_field(body, "SARP packet manifest path or URL")
    archive = extract_field(body, "Primary SARP archive or packet URL")
    evidence = extract_field(body, "Evidence links")
    return f"""You are performing External SARP review for MetaBlooms OS.

You must return only one JSON object matching schema mb.github_connector.sarp_verdict.v1.

SARP is review evidence only. You must keep these fields false:
- implementation_authorized
- promotion_authorized
- github_write_authorized
- merge_authorized

If you cannot inspect or verify a linked artifact, use verdict BLOCKED_INSUFFICIENT_EVIDENCE.

Issue title:
{issue.get("title", "")}

Manifest:
{manifest}

Primary archive or issue:
{archive}

Bounded question:
{bounded_question}

Evidence:
{evidence}
"""


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("agent response did not contain JSON object")
    return json.loads(text[start : end + 1])


def normalize_verdict(obj: dict[str, Any], reviewer: str, issue: dict[str, Any]) -> dict[str, Any]:
    body = issue.get("body") or ""
    result = dict(VERDICT_TEMPLATE)
    result.update(obj)
    result["schema"] = "mb.github_connector.sarp_verdict.v1"
    result["reviewer"] = reviewer
    result["packet"] = {
        **VERDICT_TEMPLATE["packet"],
        **(obj.get("packet") if isinstance(obj.get("packet"), dict) else {}),
    }
    result["packet"]["manifest_path_or_url"] = result["packet"].get("manifest_path_or_url") or extract_field(body, "SARP packet manifest path or URL")
    result["packet"]["primary_archive_or_issue"] = result["packet"].get("primary_archive_or_issue") or extract_field(body, "Primary SARP archive or packet URL") or str(issue.get("html_url", ""))
    result["bounded_question"] = result.get("bounded_question") or extract_field(body, "Bounded question")
    for key in ("implementation_authorized", "promotion_authorized", "github_write_authorized", "merge_authorized"):
        result[key] = False
    blocked = result.get("blocked_actions")
    if not isinstance(blocked, list):
        blocked = []
    for action in VERDICT_TEMPLATE["blocked_actions"]:
        if action not in blocked:
            blocked.append(action)
    result["blocked_actions"] = blocked
    return result


def call_openai(prompt: str) -> str:
    token = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1")
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("output_text"):
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)


def call_anthropic(prompt: str) -> str:
    token = os.environ["ANTHROPIC_API_KEY"]
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    payload = {
        "model": model,
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as response:
        data = json.loads(response.read().decode("utf-8"))
    return "\n".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")


def call_xai(prompt: str) -> str:
    token = os.environ["XAI_API_KEY"]
    model = os.environ.get("XAI_MODEL", "grok-4")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def agent_response(provider: str, prompt: str) -> str:
    if provider == "free":
        return json.dumps({
            **VERDICT_TEMPLATE,
            "verdict": "BLOCKED_INSUFFICIENT_EVIDENCE",
            "reviewer": "github-actions-free-intake",
            "decision_summary": "Free GitHub Actions intake completed. No paid model was called, so semantic External SARP approval was not performed.",
            "findings": [
                {
                    "code": "FREE_INTAKE_ONLY",
                    "detail": "This reply is a no-cost structural SARP response. Use ChatGPT UI connector or a human reviewer for semantic approval."
                }
            ],
            "next_allowed_action": "Use this free reply as an intake/completeness signal only; request human or ChatGPT UI review for a substantive SARP verdict."
        })
    if provider == "openai":
        return call_openai(prompt)
    if provider == "anthropic":
        return call_anthropic(prompt)
    if provider == "xai":
        return call_xai(prompt)
    if provider == "stub":
        return json.dumps({
            **VERDICT_TEMPLATE,
            "verdict": "BLOCKED_INSUFFICIENT_EVIDENCE",
            "reviewer": "github-actions-stub",
            "decision_summary": "Stub mode does not call an external agent. Configure provider secrets and rerun.",
        })
    raise ValueError(f"unsupported provider: {provider}")


def format_comment(verdict: dict[str, Any]) -> str:
    return "## External SARP Verdict\n\n```json\n" + json.dumps(verdict, indent=2, sort_keys=True) + "\n```\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatch a GitHub SARP issue to an agent provider and post a bounded verdict.")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--provider", choices=["free", "stub", "openai", "anthropic", "xai"], default="free")
    parser.add_argument("--post-comment", action="store_true")
    parser.add_argument("--out", default="runtime_work/SARP_AGENT_VERDICT.md")
    args = parser.parse_args(argv)

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise SystemExit("GITHUB_TOKEN is required")
    issue = fetch_issue(args.owner, args.repo, args.issue_number, github_token)
    prompt = build_review_prompt(issue)
    raw = agent_response(args.provider, prompt)
    try:
        verdict = normalize_verdict(extract_json_object(raw), f"github-actions-{args.provider}", issue)
    except Exception as exc:
        verdict = normalize_verdict({
            "verdict": "BLOCKED_INSUFFICIENT_EVIDENCE",
            "decision_summary": f"Agent response could not be parsed as SARP JSON: {type(exc).__name__}: {exc}",
            "findings": [{"raw_response_prefix": raw[:1000]}],
        }, f"github-actions-{args.provider}", issue)
    comment = format_comment(verdict)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(comment, encoding="utf-8")
    if args.post_comment:
        post_issue_comment(args.owner, args.repo, args.issue_number, github_token, comment)
    print(comment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
