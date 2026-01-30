from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import GitError


def extract_diff(text: str) -> str:

    return _extract_diff_block(text)


def _strip_markdown_fences(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    out: list[str] = []
    for ln in lines:
        if ln.strip().startswith("```"):
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def _extract_diff_block(text: str) -> str:
    t = _strip_markdown_fences(text)

    idx = t.find("diff --git ")
    if idx != -1:
        return t[idx:].strip() + "\n"

    idx2 = t.find("--- ")
    if idx2 != -1:
        return t[idx2:].strip() + "\n"

    return t.strip() + "\n"


def _normalize_dev_null(diff: str) -> str:

    lines = diff.splitlines()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("--- "):
            rhs = s[4:].strip()
            rhs_norm = rhs.replace("\\", "/")
            rhs_norm = rhs_norm.lstrip("./")
            if rhs_norm == "dev/null" or rhs_norm.endswith("/dev/null") or rhs_norm.endswith("a/dev/null"):
                out.append("--- /dev/null")
                continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def _run_git(repo_dir: Path, args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        input=input_text.encode("utf-8") if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def apply_patch(repo_dir: Path, diff_text: str) -> None:

    repo_dir = Path(repo_dir)
    diff = _extract_diff_block(diff_text)
    diff = _normalize_dev_null(diff)

    if "diff --git " not in diff and not diff.lstrip().startswith("--- "):
        raise GitError("LLM did not return a diff/patch that can be applied.")

    p = _run_git(repo_dir, ["apply", "--whitespace=nowarn", "--3way", "-"], input_text=diff)
    if p.returncode == 0:
        return

    p2 = _run_git(repo_dir, ["apply", "--whitespace=nowarn", "-"], input_text=diff)
    if p2.returncode == 0:
        return

    stderr = (p.stderr or b"").decode("utf-8", errors="ignore").strip()
    stderr2 = (p2.stderr or b"").decode("utf-8", errors="ignore").strip()
    raise GitError(
        "git apply failed.\n\n"
        f"stderr(3way): {stderr}\n\n"
        f"stderr: {stderr2}\n\n"
        "Tip: Ensure patch is a proper unified diff starting with 'diff --git ...' "
        "and for new files uses '--- /dev/null'."
    )
