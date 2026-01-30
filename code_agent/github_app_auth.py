from __future__ import annotations

import time
import json
import urllib.request

import jwt

from .errors import GitHubError


class GitHubAppAuth:
    def __init__(self, app_id: str | None, private_key_path: str | None):
        if not app_id:
            raise ValueError("GITHUB_APP_ID is required")
        if not private_key_path:
            raise ValueError("GITHUB_APP_PRIVATE_KEY_PATH is required")
        self.app_id = app_id
        self.private_key_path = private_key_path

    def _load_private_key(self) -> str:
        with open(self.private_key_path, "r", encoding="utf-8") as f:
            return f.read()

    def create_jwt(self) -> str:
        private_key = self._load_private_key()
        now = int(time.time())
        payload = {
            "iat": now - 5,
            "exp": now + 9 * 60,  # <= 10 minutes
            "iss": self.app_id,
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    def get_installation_token(self, installation_id: int) -> str:
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        token_jwt = self.create_jwt()
        headers = {
            "Authorization": f"Bearer {token_jwt}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "agent-service",
        }
        req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            t = data.get("token")
            if not t:
                raise GitHubError(f"Missing token in response: {data}")
            return str(t)
        except Exception as e:
            raise GitHubError(f"Failed to get installation token: {e}") from e
