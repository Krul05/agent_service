from __future__ import annotations

import re
from dataclasses import dataclass

ITER_RE = re.compile(r"^agent:iter-(\d+)$")


@dataclass(frozen=True)
class IterationState:
    current_iter: int
    labels: list[str]


def read_iteration(labels: list[str]) -> IterationState:
    it = -1
    for lb in labels:
        m = ITER_RE.match(lb)
        if m:
            it = max(it, int(m.group(1)))
    return IterationState(current_iter=it, labels=labels[:])


def set_iteration_labels(labels: list[str], new_iter: int, running: bool = True, done: bool = False, stopped: bool = False) -> list[str]:
    out = [lb for lb in labels if not ITER_RE.match(lb)]
    out = [lb for lb in out if lb not in ("agent:running", "agent:done", "agent:stopped")]

    if running:
        out.append("agent:running")
    if done:
        out.append("agent:done")
    if stopped:
        out.append("agent:stopped")

    if new_iter >= 0:
        out.append(f"agent:iter-{new_iter}")

    return sorted(set(out))
