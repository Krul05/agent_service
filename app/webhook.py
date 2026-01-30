from __future__ import annotations

from pathlib import Path
from typing import Any

from code_agent.github_app_auth import GitHubAppAuth
from code_agent.github_client import GitHubClient, RepoRef
from code_agent.runner import CodeAgentRunner


def _get_installation_id(payload: dict[str, Any]) -> int:
    inst = payload.get("installation") or {}
    inst_id = inst.get("id")
    if not inst_id:
        raise ValueError("Missing installation.id in payload")
    return int(inst_id)


def _get_repo_from_standard_payload(payload: dict[str, Any]) -> tuple[RepoRef, str]:
    repo = payload.get("repository") or {}
    full_name = repo.get("full_name")
    clone_url = repo.get("clone_url")
    if not full_name:
        raise ValueError("Missing repository.full_name")
    if not clone_url:
        clone_url = f"https://github.com/{full_name}.git"
    owner, name = str(full_name).split("/", 1)
    return RepoRef(owner=owner, name=name), str(clone_url)


def _ensure_upsert_methods_exist(gh: GitHubClient) -> None:
    if not hasattr(gh, "upsert_file"):
        raise RuntimeError(
            "GitHubClient.upsert_file() is missing. "
            "Add get_content() + upsert_file() methods to code_agent/github_client.py"
        )


def _collect_template_files() -> list[tuple[str, bytes]]:

    root = Path(__file__).resolve().parents[1]

    files: list[tuple[str, bytes]] = []

    templates_root = root / "templates"
    if templates_root.exists():
        for p in templates_root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(templates_root).as_posix()
                files.append((rel, p.read_bytes()))

    reviewer_src = root / "code_reviewer"
    if not reviewer_src.exists():
        raise FileNotFoundError(f"Expected reviewer source folder not found: {reviewer_src}")

    for p in reviewer_src.rglob("*"):
        if p.is_file():
            rel = "reviewer/" + p.relative_to(reviewer_src).as_posix()
            files.append((rel, p.read_bytes()))

    if not files:
        raise RuntimeError("No template files collected. Check templates/ and code_reviewer/ structure.")

    return files


def _with_token_in_https_url(clone_url: str, token: str) -> str:
    if not clone_url.startswith("https://"):
        return clone_url
    return clone_url.replace("https://", f"https://x-access-token:{token}@")


# ----------------------------
# Handlers
# ----------------------------
def handle_installation_repositories_added(payload: dict[str, Any], auth: GitHubAppAuth) -> dict[str, Any]:
    inst_id = _get_installation_id(payload)
    token = auth.get_installation_token(inst_id)
    gh = GitHubClient(token)

    _ensure_upsert_methods_exist(gh)

    repos_added = payload.get("repositories_added") or []
    if not isinstance(repos_added, list) or not repos_added:
        return {"status": "ok", "action": "installation_repositories.added", "results": [], "note": "no repos"}

    files = _collect_template_files()

    results: list[dict[str, Any]] = []
    for r in repos_added:
        full_name = r.get("full_name")
        if not full_name:
            continue

        owner, name = str(full_name).split("/", 1)
        repo_ref = RepoRef(owner=owner, name=name)

        created = 0
        updated = 0

        for repo_path, content_bytes in files:
            existed = gh.upsert_file(
                repo=repo_ref,
                path=repo_path,
                content_bytes=content_bytes,
                message="Install AI reviewer workflow and scripts",
            )
            if existed:
                updated += 1
            else:
                created += 1

        results.append({"repo": str(full_name), "created": created, "updated": updated})

    return {"status": "ok", "action": "installation_repositories.added", "results": results}


def handle_issue_opened(payload: dict[str, Any], auth: GitHubAppAuth, runner: CodeAgentRunner) -> dict[str, Any]:
    inst_id = _get_installation_id(payload)
    token = auth.get_installation_token(inst_id)
    gh = GitHubClient(token)

    repo_ref, clone_url = _get_repo_from_standard_payload(payload)
    repo_url = _with_token_in_https_url(clone_url, token)

    issue = payload.get("issue") or {}
    issue_number = issue.get("number")
    if not issue_number:
        raise ValueError("Missing issue.number")

    pr_url = runner.solve_issue(
        gh=gh,
        repo=repo_ref,
        repo_url=repo_url,
        issue_number=int(issue_number),
        installation_id=inst_id,
    )

    return {
        "status": "ok",
        "action": "issues.opened",
        "repo": repo_ref.full_name,
        "issue": int(issue_number),
        "pr_url": pr_url,
    }


def handle_review_submitted(payload: dict[str, Any], auth: GitHubAppAuth, runner: CodeAgentRunner) -> dict[str, Any]:
    inst_id = _get_installation_id(payload)
    token = auth.get_installation_token(inst_id)
    gh = GitHubClient(token)

    repo_ref, clone_url = _get_repo_from_standard_payload(payload)
    repo_url = _with_token_in_https_url(clone_url, token)

    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    if not pr_number:
        raise ValueError("Missing pull_request.number")

    review = payload.get("review") or {}
    review_body = (review.get("body") or "").strip()

    result = runner.on_reviewer_feedback(
        gh=gh,
        repo=repo_ref,
        repo_url=repo_url,
        pr_number=int(pr_number),
        review_body=review_body,
        installation_id=inst_id,
    )

    return {
        "status": "ok",
        "action": "pull_request_review.submitted",
        "repo": repo_ref.full_name,
        "pr": int(pr_number),
        "result": result,
    }
