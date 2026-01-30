from __future__ import annotations

import json
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from app.security import verify_github_signature
from app.settings import SETTINGS

from code_agent.github_app_auth import GitHubAppAuth
from code_agent.runner import CodeAgentRunner
from app.webhook import (
    handle_installation_repositories_added,
    handle_issue_opened,
    handle_review_submitted,
)

app = FastAPI(title="Agent Service", version="0.1.0")

auth = GitHubAppAuth(
    app_id=SETTINGS.github_app_id,
    private_key_path=SETTINGS.github_app_private_key_path,
)

runner = CodeAgentRunner(
    api_key=SETTINGS.api_key,
    model=SETTINGS.model,
    llm_base_url=SETTINGS.llm_base_url,
    base_branch=SETTINGS.base_branch,
    max_iters=SETTINGS.max_iters,
    workdir=SETTINGS.workdir,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _infer_event(headers: dict[str, str], payload: dict[str, Any]) -> str:
    event = (headers.get("X-GitHub-Event") or "").strip()
    if event:
        return event
    # fallback if empty
    if "repositories_added" in payload or "repositories_removed" in payload:
        return "installation_repositories"
    if "issue" in payload:
        return "issues"
    if "pull_request" in payload and "review" in payload:
        return "pull_request_review"
    return ""


@app.post("/webhook")
async def webhook(req: Request, background: BackgroundTasks) -> dict[str, Any]:
    raw = await req.body()

    secret = SETTINGS.github_webhook_secret
    sig256 = req.headers.get("X-Hub-Signature-256")
    if not secret or not verify_github_signature(secret, raw, sig256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = (payload.get("action") or "").lower()
    event = _infer_event(dict(req.headers), payload)
    if not event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    if event == "installation_repositories":
        if action == "added":
            background.add_task(handle_installation_repositories_added, payload, auth)
            return {"status": "accepted", "event": event, "action": action}
        return {"status": "ignored", "event": event, "action": action}

    if event == "issues":
        if action == "opened":
            background.add_task(handle_issue_opened, payload, auth, runner)
            return {"status": "accepted", "event": event, "action": action}
        return {"status": "ignored", "event": event, "action": action}

    if event == "pull_request_review":
        if action == "submitted":
            background.add_task(handle_review_submitted, payload, auth, runner)
            return {"status": "accepted", "event": event, "action": action}
        return {"status": "ignored", "event": event, "action": action}

    return {"status": "ignored", "event": event, "action": action}
