class AgentError(RuntimeError):
    pass


class LLMError(AgentError):
    pass


class GitError(AgentError):
    pass


class GitHubError(AgentError):
    pass
