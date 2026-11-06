class AgentError(Exception):
    """A safe, actionable AI execution failure."""


class ConfigurationError(AgentError):
    pass


class ModelOutputError(AgentError):
    pass


class RequestBudgetExceeded(AgentError):
    pass


class StaleReviewError(AgentError):
    pass
