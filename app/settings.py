from __future__ import annotations

import os
from dataclasses import dataclass

try:
    import dotenv
except Exception:
    dotenv = None


def _load_env() -> None:
    if dotenv is not None:
        try:
            dotenv.load_dotenv()
        except Exception:
            pass


_load_env()


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))

    github_app_id: str | None = os.getenv("GITHUB_APP_ID")
    github_app_private_key_path: str | None = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
    github_webhook_secret: str | None = os.getenv("GITHUB_WEBHOOK_SECRET")

    api_key: str | None = os.getenv("API_KEY")
    model: str = os.getenv("MODEL", "gpt://ajectldinp5kbvbuii6r/yandexgpt-lite")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://llm.api.cloud.yandex.net")

    base_branch: str = os.getenv("BASE_BRANCH", "master")
    max_iters: int = int(os.getenv("MAX_ITERS", "5"))
    workdir: str = os.getenv("WORKDIR", "/tmp/agent-workdir")


SETTINGS = Settings()
