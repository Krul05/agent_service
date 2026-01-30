from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from .errors import LLMError
from .feedback import parse_review
from .git_workspace import Workspace
from .github_client import GitHubClient, RepoRef
from .labels import read_iteration, set_iteration_labels
from .patch_utils import apply_patch, extract_diff
from .prompts import SYSTEM_CODE_AGENT, prompt_fix_from_feedback, prompt_solve_issue


class CodeAgentRunner:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        llm_base_url: str,
        base_branch: str,
        max_iters: int,
        workdir: str,
    ):
        if not api_key:
            raise ValueError("API_KEY is required")

        self.api_key = api_key
        self.model = model
        self.llm_base_url = llm_base_url.rstrip("/")  # <-- ключевая строка
        self.base_branch = base_branch
        self.max_iters = max_iters
        self.workdir = Path(workdir)

    def _call_llm(self, user_prompt: str) -> str:
        import json
        import urllib.request
        import urllib.error

        url = f"{self.llm_base_url.rstrip('/')}/foundationModels/v1/completion"

        payload = {
            "modelUri": self.model,
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": 2000,
            },
            "messages": [
                {"role": "system", "text": SYSTEM_CODE_AGENT},
                {"role": "user", "text": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            raise LLMError(f"LLM HTTP {e.code} {e.reason}. Body: {body}") from e
        except Exception as e:
            raise LLMError(f"LLM call failed: {e}") from e

        obj = json.loads(raw)
        try:
            return obj["result"]["alternatives"][0]["message"]["text"]
        except Exception as e:
            raise LLMError(f"Unexpected LLM response: {obj}") from e

    # -------- Helpers ----------
    def _repo_dir(self, repo: RepoRef, key: str) -> Path:
        safe = f"{repo.owner}_{repo.name}_{key}".replace("/", "_")
        return self.workdir / safe

    def _find_or_create_pr(
        self,
        gh: GitHubClient,
        repo: RepoRef,
        branch: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        pulls = gh.list_open_pulls(repo)
        for pr in pulls:
            head = ((pr.get("head") or {}).get("ref") or "")
            if head == branch:
                return pr
        return gh.create_pr(repo, title=title, body=body, head=branch, base=self.base_branch)

    def _extract_issue_number_from_text(self, text: str) -> int | None:
        import re

        m = re.search(r"#(\d+)", text or "")
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def solve_issue(
        self,
        gh: GitHubClient,
        repo: RepoRef,
        repo_url: str,
        issue_number: int,
        installation_id: int,
    ) -> str:

        issue = gh.get_issue(repo, issue_number)
        issue_title = issue.get("title") or ""
        issue_body = issue.get("body") or ""

        repo_dir = self._repo_dir(repo, f"issue{issue_number}")
        ws = Workspace(path=repo_dir, base_branch=self.base_branch)
        r = ws.ensure_cloned(repo_url)

        branch = f"issue-{issue_number}"
        ws.checkout_new_branch(r, branch)

        answer = self._call_llm(prompt_solve_issue(issue_title, issue_body))
        diff = extract_diff(answer)
        if not diff:
            raise LLMError("LLM did not return ```diff``` block for solve_issue")

        apply_patch(repo_dir, diff)
        changed = ws.commit_all(r, f"Implement issue #{issue_number}")
        if not changed:
            gh.create_issue_comment(
                repo,
                issue_number,
                "Agent: no changes were produced. Please уточните требования/критерии готовности.",
            )
            return ""

        ws.set_origin_with_token(r, repo_url, gh.token)
        ws.push(r, branch)

        pr_obj = self._find_or_create_pr(
            gh,
            repo,
            branch=branch,
            title=f"Implement issue #{issue_number}: {issue_title}",
            body=f"Closes #{issue_number}\n\nAgent installation: {installation_id}",
        )
        pr_url = pr_obj.get("html_url") or ""
        pr_number = int(pr_obj.get("number") or 0)

        if pr_number:
            try:
                labels = gh.get_issue_labels(repo, pr_number)
                new_labels = set_iteration_labels(labels, new_iter=0, running=True)
                gh.replace_issue_labels(repo, pr_number, new_labels)
            except Exception:
                pass

        return pr_url

    def on_reviewer_feedback(
        self,
        gh: GitHubClient,
        repo: RepoRef,
        repo_url: str,
        pr_number: int,
        review_body: str,
        installation_id: int,  # пока не используется, но оставляем для расширений/логов
    ) -> dict[str, Any]:

        verdict = parse_review(review_body)

        try:
            labels = gh.get_issue_labels(repo, pr_number)
        except Exception:
            labels = []

        st = read_iteration(labels)
        current_iter = st.current_iter if st.current_iter >= 0 else 0

        if verdict.verdict == "PASS":
            try:
                new_labels = set_iteration_labels(labels, new_iter=current_iter, running=False, done=True)
                gh.replace_issue_labels(repo, pr_number, new_labels)
            except Exception:
                pass
            return {"verdict": "PASS", "action": "stop", "iter": current_iter}

        if current_iter >= self.max_iters:
            try:
                new_labels = set_iteration_labels(labels, new_iter=current_iter, running=False, stopped=True)
                gh.replace_issue_labels(repo, pr_number, new_labels)
                gh.create_issue_comment(
                    repo,
                    pr_number,
                    (
                        f"Agent stopped: max iterations reached ({self.max_iters}).\n\n"
                        "Last reviewer feedback:\n\n"
                        f"{review_body}"
                    ),
                )
            except Exception:
                pass
            return {"verdict": "FAIL", "action": "stopped_max_iters", "iter": current_iter}

        pr = gh.get_pull(repo, pr_number)
        pr_body = pr.get("body") or ""
        issue_num = self._extract_issue_number_from_text(pr_body)

        if issue_num:
            issue = gh.get_issue(repo, issue_num)
            issue_title = issue.get("title") or ""
            issue_body = issue.get("body") or ""
        else:
            issue_title, issue_body = "(unknown issue)", ""

        repo_dir = self._repo_dir(repo, f"pr{pr_number}")
        ws = Workspace(path=repo_dir, base_branch=self.base_branch)
        r = ws.ensure_cloned(repo_url)

        head = ((pr.get("head") or {}).get("ref") or "")
        if not head:
            raise RuntimeError("Cannot determine PR head branch")

        r.git.fetch("--all")
        r.git.checkout(head)

        feedback_text = review_body
        fix_answer = self._call_llm(prompt_fix_from_feedback(issue_title, issue_body, feedback_text))
        fix_diff = extract_diff(fix_answer)
        if not fix_diff:
            raise LLMError("LLM did not return ```diff``` block for fix iteration")

        apply_patch(repo_dir, fix_diff)

        committed = ws.commit_all(r, f"Fix iteration {current_iter + 1} for PR #{pr_number} (review feedback)")
        if not committed:
            try:
                new_labels = set_iteration_labels(labels, new_iter=current_iter, running=False, stopped=True)
                gh.replace_issue_labels(repo, pr_number, new_labels)
                gh.create_issue_comment(
                    repo,
                    pr_number,
                    (
                        "Agent could not produce any code changes for the requested fixes.\n"
                        "Stopping to avoid infinite loop.\n\n"
                        f"Reviewer feedback:\n\n{review_body}"
                    ),
                )
            except Exception:
                pass
            return {"verdict": "FAIL", "action": "no_changes_stop", "iter": current_iter}

        ws.set_origin_with_token(r, repo_url, gh.token)
        ws.push(r, head)

        try:
            labels2 = gh.get_issue_labels(repo, pr_number)
            new_labels = set_iteration_labels(labels2, new_iter=current_iter + 1, running=True)
            gh.replace_issue_labels(repo, pr_number, new_labels)
        except Exception:
            pass

        return {
            "verdict": "FAIL",
            "action": "pushed_fix",
            "branch": head,
            "iter": current_iter + 1,
        }
