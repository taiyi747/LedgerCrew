class AgentError(Exception):
    """A safe, actionable AI execution failure."""


class ConfigurationError(AgentError):
    pass


class ModelOutputError(AgentError):
    pass


class RequestBudgetExceeded(AgentError):
    pass


class ModelRateLimitError(AgentError):
    pass


class ModelServiceUnavailable(AgentError):
    pass


class ModelTimeoutError(AgentError):
    pass


class ModelNetworkError(AgentError):
    pass


class StaleReviewError(AgentError):
    pass
