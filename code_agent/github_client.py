from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, message: str, body: str | None = None):
        super().__init__(f"GitHub API error {status}: {message}" + (f" | body={body}" if body else ""))
        self.status = status
        self.message = message
        self.body = body


class GitHubClient:


    def __init__(self, token: str, api_base: str = "https://api.github.com"):
        if not token:
            raise ValueError("GitHub token is required")
        self.token = token
        self.api_base = api_base.rstrip("/")

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "agent-service",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                if not raw.strip():
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = None
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = None
            raise GitHubAPIError(e.code, e.reason, body) from e
        except Exception as e:
            raise RuntimeError(f"GitHub request failed: {method} {url}: {e}") from e

    def get_issue(self, repo: RepoRef, issue_number: int) -> dict[str, Any]:
        url = f"{self.api_base}/repos/{repo.full_name}/issues/{issue_number}"
        return self._request("GET", url)

    def create_issue_comment(self, repo: RepoRef, issue_number: int, body: str) -> dict[str, Any]:
        url = f"{self.api_base}/repos/{repo.full_name}/issues/{issue_number}/comments"
        return self._request("POST", url, payload={"body": body})

    def list_open_pulls(self, repo: RepoRef, per_page: int = 50) -> list[dict[str, Any]]:
        url = f"{self.api_base}/repos/{repo.full_name}/pulls?state=open&per_page={per_page}"
        data = self._request("GET", url)
        return data if isinstance(data, list) else []

    def get_pull(self, repo: RepoRef, pr_number: int) -> dict[str, Any]:
        url = f"{self.api_base}/repos/{repo.full_name}/pulls/{pr_number}"
        return self._request("GET", url)

    def create_pr(self, repo: RepoRef, title: str, body: str, head: str, base: str) -> dict[str, Any]:
        url = f"{self.api_base}/repos/{repo.full_name}/pulls"
        payload = {"title": title, "body": body, "head": head, "base": base}
        return self._request("POST", url, payload=payload)

    def get_issue_labels(self, repo: RepoRef, issue_number: int) -> list[str]:
        url = f"{self.api_base}/repos/{repo.full_name}/issues/{issue_number}/labels"
        data = self._request("GET", url)
        out: list[str] = []
        if isinstance(data, list):
            for it in data:
                name = (it or {}).get("name")
                if name:
                    out.append(str(name))
        return out

    def replace_issue_labels(self, repo: RepoRef, issue_number: int, labels: list[str]) -> list[dict[str, Any]]:

        url = f"{self.api_base}/repos/{repo.full_name}/issues/{issue_number}/labels"
        data = self._request("PUT", url, payload={"labels": labels})
        return data if isinstance(data, list) else []

    def get_content(self, repo: RepoRef, path: str) -> dict[str, Any] | None:

        url = f"{self.api_base}/repos/{repo.full_name}/contents/{path}"
        try:
            data = self._request("GET", url)
            return data if isinstance(data, dict) else None
        except GitHubAPIError as e:
            if e.status == 404:
                return None
            raise

    def upsert_file(self, repo: RepoRef, path: str, content_bytes: bytes, message: str) -> bool:

        import base64

        existing = self.get_content(repo, path)
        sha = None
        if isinstance(existing, dict) and existing.get("sha"):
            sha = existing["sha"]

        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content_bytes).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha

        url = f"{self.api_base}/repos/{repo.full_name}/contents/{path}"
        self._request("PUT", url, payload=payload)
        return bool(sha)
