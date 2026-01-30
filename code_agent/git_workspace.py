from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import git

from .errors import GitError


@dataclass
class Workspace:
    path: Path
    base_branch: str

    def ensure_cloned(self, repo_url: str) -> git.Repo:
        try:
            if (self.path / ".git").exists():
                return git.Repo(str(self.path))
            self.path.mkdir(parents=True, exist_ok=True)
            return git.Repo.clone_from(repo_url, str(self.path))
        except Exception as e:
            raise GitError(f"Failed to clone/open repo: {e}") from e

    def checkout_new_branch(self, repo: git.Repo, branch: str) -> None:
        try:
            repo.git.fetch("--all")
            repo.git.checkout(self.base_branch)
            repo.git.pull("origin", self.base_branch)
            repo.git.checkout("-B", branch)
        except Exception as e:
            raise GitError(f"Failed to checkout branch: {e}") from e

    def commit_all(self, repo: git.Repo, message: str) -> bool:
        repo.git.add(A=True)
        if not repo.is_dirty(untracked_files=True):
            return False
        repo.index.commit(message)
        return True

    def set_origin_with_token(self, repo: git.Repo, clone_url: str, token: str) -> None:
        """
        HTTPS remote with x-access-token to push.
        IMPORTANT: do not log the url with token.
        """
        if clone_url.startswith("https://"):
            authed = "https://x-access-token:" + token + "@" + clone_url[len("https://") :]
        else:

            authed = clone_url
        repo.git.remote("set-url", "origin", authed)

    def push(self, repo: git.Repo, branch: str) -> None:
        try:
            repo.git.push("-u", "origin", branch, "--force-with-lease")
        except Exception as e:
            raise GitError(f"Failed to push branch: {e}") from e
