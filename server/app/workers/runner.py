"""Adapter boundary for a future workflow runtime; no workflow implementation here."""

from typing import Protocol


class WorkflowRunner(Protocol):
    async def run(self, run_id: str) -> None: ...

    async def resume(self, run_id: str) -> None: ...
