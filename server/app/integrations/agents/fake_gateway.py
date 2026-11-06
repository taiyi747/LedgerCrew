"""Explicitly configured development/test fake; never enabled in production."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import JsonValue

from app.core.config import get_settings
from app.db.types import utc_now
from app.integrations.agents.contracts import AgentInvocationRequest, AgentInvocationResponse


@dataclass(frozen=True)
class FakeResult:
    status: Literal["succeeded", "failed", "paused"]
    output_payload: dict[str, JsonValue] | None = None
    error: str | None = None
    provider_metadata: dict[str, JsonValue] = field(default_factory=lambda: {"provider": "fake"})


class FakeAgentGateway:
    def __init__(self, results: dict[str, FakeResult]) -> None:
        self.results = results
        self.requests: list[AgentInvocationRequest] = []

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResponse:
        if get_settings().environment == "production":
            raise RuntimeError("FakeAgentGateway is disabled in production")
        self.requests.append(request)
        if request.task_type not in self.results:
            raise RuntimeError(f"No fake result configured for {request.task_type}")
        result = self.results[request.task_type]
        started = utc_now()
        return AgentInvocationResponse(
            task_id=request.task_id, status=result.status, output_payload=result.output_payload,
            error=result.error, started_at=started,
            finished_at=utc_now() if result.status != "paused" else None,
            provider_metadata=result.provider_metadata,
        )
