from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from .prompt import SYSTEM_PROMPT


@dataclass(frozen=True)
class PRContext:
    owner: str
    repo: str
    pr_number: int
    pr_title: str
    pr_body: str
    base_sha: str
    head_sha: str


def read_event() -> dict[str, Any]:
    path = os.getenv("GITHUB_EVENT_PATH")
    if not path or not os.path.exists(path):
        raise RuntimeError("GITHUB_EVENT_PATH is not set or file does not exist.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_pr_context(evt: dict[str, Any]) -> PRContext:
    pr = evt.get("pull_request") or {}
    repo = evt.get("repository") or {}
    owner = (repo.get("owner") or {}).get("login") or ""
    name = repo.get("name") or ""
    number = pr.get("number")
    if not owner or not name or not number:
        raise RuntimeError("Unable to parse PR context from event payload.")

    base_sha = (pr.get("base") or {}).get("sha") or ""
    head_sha = (pr.get("head") or {}).get("sha") or ""
    if not base_sha or not head_sha:
        raise RuntimeError("Unable to read base/head sha from event payload.")

    return PRContext(
        owner=owner,
        repo=name,
        pr_number=int(number),
        pr_title=pr.get("title") or "",
        pr_body=pr.get("body") or "",
        base_sha=base_sha,
        head_sha=head_sha,
    )


def gh_api_request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "ai-reviewer-agent",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


ISSUE_REF_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|ref(?:erence)?|#)\s*#?(\d+)", re.IGNORECASE)


def extract_issue_number(pr_body: str) -> Optional[int]:

    if not pr_body:
        return None
    m = ISSUE_REF_RE.search(pr_body)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def get_issue_text(owner: str, repo: str, issue_number: int, token: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    data = gh_api_request("GET", url, token)
    title = data.get("title") or ""
    body = data.get("body") or ""
    return f"# Issue #{issue_number}\n\n## Title\n{title}\n\n## Body\n{body}\n"


def git_diff(base_sha: str, head_sha: str) -> str:

    subprocess.run(["git", "fetch", "--all", "--tags", "--prune"], check=False)
    p = subprocess.run(
        ["git", "diff", f"{base_sha}...{head_sha}"],
        capture_output=True,
        text=True,
        check=False,
    )
    diff = p.stdout or ""
    max_chars = 120_000
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n\n# NOTE: diff truncated due to size.\n"
    return diff


def read_ci_context() -> tuple[str, str]:

    ci_result = os.getenv("CI_RESULT", "unknown")
    ci_output_path = os.getenv("CI_OUTPUT_PATH", "")
    ci_output = ""
    if ci_output_path and os.path.exists(ci_output_path):
        with open(ci_output_path, "r", encoding="utf-8", errors="ignore") as f:
            ci_output = f.read()
        if len(ci_output) > 60_000:
            ci_output = ci_output[:60_000] + "\n\n# NOTE: CI output truncated.\n"
    return ci_result, ci_output


def call_openrouter(model: str, api_key: str, user_prompt: str) -> str:

    base_url = os.getenv("LLM_BASE_URL", "https://llm.api.cloud.yandex.net").rstrip("/")
    url = base_url + "/v1/chat/completions"

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    folder_id = os.getenv("YANDEX_FOLDER_ID")
    if folder_id:
        headers["x-folder-id"] = folder_id

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")

    obj = json.loads(raw)
    try:
        return obj["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Unexpected LLM response: {obj}") from e


def parse_verdict(text: str) -> str:
    m = VERDICT_RE.search(text or "")
    return m.group(1).upper() if m else "FAIL"


def post_pr_review(owner: str, repo: str, pr_number: int, token: str, body: str, verdict: str) -> None:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    event = "APPROVE" if verdict == "PASS" else "REQUEST_CHANGES"
    gh_api_request("POST", url, token, payload={"body": body, "event": event})


def write_job_summary(md: str) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(md)
        if not md.endswith("\n"):
            f.write("\n")


def build_prompt(ctx: PRContext, issue_text: str, diff_text: str, ci_result: str, ci_output: str) -> str:
    return f"""Ты ревьювишь Pull Request.

# PR
Title: {ctx.pr_title}

# PR Body
{ctx.pr_body}

{issue_text}

# CI Result
{ci_result}

# CI Output
```text
{ci_output}

{diff_text}

Сформируй результат строго по формату (VERDICT/PROBLEMS/NEXT_ACTIONS/TEST_SUGGESTIONS).
"""

def main() -> None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required.")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise SystemExit("API_KEY secret is required.")

    model = os.getenv("MODEL", "gpt://ajectldinp5kbvbuii6r/yandexgpt-lite")

    evt = read_event()
    ctx = parse_pr_context(evt)

    issue_number = extract_issue_number(ctx.pr_body)
    issue_text = ""
    if issue_number is not None:
        try:
            issue_text = get_issue_text(ctx.owner, ctx.repo, issue_number, token)
        except Exception:
            issue_text = f"# Issue\nUnable to fetch issue #{issue_number}\n"

    diff_text = git_diff(ctx.base_sha, ctx.head_sha)

    ci_result, ci_output = read_ci_context()

    user_prompt = build_prompt(
        ctx=ctx,
        issue_text=issue_text,
        diff_text=diff_text,
        ci_result=ci_result,
        ci_output=ci_output,
    )

    review_text = call_openrouter(model=model, api_key=api_key, user_prompt=user_prompt)
    verdict = parse_verdict(review_text)

    post_pr_review(ctx.owner, ctx.repo, ctx.pr_number, token, review_text, verdict)

    write_job_summary(
        f"## AI Reviewer Result\n\n**PR:** #{ctx.pr_number}\n\n**VERDICT:** {verdict}\n\n"
        f"### Review\n\n{review_text}\n"
    )

    print(f"VERDICT={verdict}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise