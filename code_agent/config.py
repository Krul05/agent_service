from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    api_key: str
    model: str
    llm_base_url: str
    base_branch: str
    max_iters: int
    workdir: str
