from typing import Protocol

from app.integrations.agents.contracts import AgentInvocationRequest, AgentInvocationResponse


class AgentGateway(Protocol):
    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResponse: ...
