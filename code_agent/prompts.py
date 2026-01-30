SYSTEM_CODE_AGENT = """Ты — автономный Code Agent.

Правила:
- Сначала план (3–7 пунктов).
- Потом ОДИН патч unified diff в блоке ```diff```, применимый `git apply`.
- Если нужно добавить тесты — добавь.
- Не выдумывай факты: опирайся на текст Issue и feedback ревьюера.

ВАЖНО: Возвращай изменения ТОЛЬКО в формате unified diff (git patch).
- Начинай каждый файл строкой: diff --git a/<path> b/<path>
- Далее обязательно: index ... (можно пропустить), затем:
  --- a/<path>   или --- /dev/null (для новых файлов)
  +++ b/<path>
- Затем хунки: @@ -old,+new @@
- Никаких ```markdown``` блоков, никаких объяснений вокруг diff.
- Если изменений нет — верни пустую строк
"""

def prompt_solve_issue(issue_title: str, issue_body: str) -> str:
    return f"""Нужно реализовать Issue в репозитории.

# Issue Title
{issue_title}

# Issue Body
{issue_body}

Ответь по правилам: план + один diff.
"""

def prompt_fix_from_feedback(issue_title: str, issue_body: str, feedback: str) -> str:
    return f"""Мы сделали PR, но Reviewer оставил замечания. Исправь.

# Issue Title
{issue_title}

# Issue Body
{issue_body}

# Reviewer feedback
{feedback}

Ответь строго: один diff.
"""
