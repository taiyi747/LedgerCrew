"""Durable lease ownership, fencing, heartbeat and crash recovery."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise

from app.agents.errors import ModelRateLimitError
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import make_engine
from app.db.types import utc_now
from app.integrations.agents.fake_gateway import FakeAgentGateway, FakeResult
from app.models import AgentTask, WorkerInstance
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service, worker_service
from scripts.run_agent_tasks import run_once


def _task(order_id: str, key: str) -> AgentTaskCreate:
    return AgentTaskCreate(order_id=order_id, agent_role="customer_reception",
                           task_type="customer_reception", idempotency_key=key,
                           correlation_id=key,
                           input_payload={"order_id": order_id, "customer_message": key})


def test_atomic_claim_heartbeat_expiry_and_fencing(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                task = await agent_service.create_task(db, _task(order_id, "lease-test"))
                first = await worker_service.register(db)
                second = await worker_service.register(db)

            async def claim(worker_id):
                async with sessions() as db:
                    return await worker_service.claim_next(db, worker_id)

            claims = await asyncio.gather(claim(first.id), claim(second.id))
            assert sum(item is not None for item in claims) == 1
            owner = first if claims[0] else second
            contender = second if claims[0] else first
            task_id, generation = next(item for item in claims if item is not None)
            assert task_id == task.id and generation == 1
            async with sessions() as db:
                assert await worker_service.heartbeat(db, owner.id, task_id, generation)
                assert not await worker_service.heartbeat(db, contender.id, task_id, generation)
                await agent_service.start_task(db, task_id)
                task = await db.get(AgentTask, task_id)
                task.lease_expires_at = utc_now() - timedelta(seconds=1)
                await db.commit()
                assert await worker_service.recover_expired(db) == [task_id]
                assert task.status == "retrying"
                assert task.next_attempt_at > utc_now()
                assert (await db.get(WorkerInstance, owner.id)).status == "lost"
                assert not await worker_service.heartbeat(db, owner.id, task_id, generation)
                with pytest.raises(AppError, match="lease"):
                    await agent_service.invoke_task(db, task_id, FakeAgentGateway({}),
                                                    lease_owner=owner.id, lease_generation=generation)
                task.next_attempt_at = utc_now() - timedelta(seconds=1)
                await db.commit()
            async with sessions() as db:
                new_claim = await worker_service.claim_next(db, contender.id)
                assert new_claim == (task_id, 2)
                await agent_service.start_task(db, task_id)
                await worker_service.abandon(db, contender.id, task_id, 2)
                abandoned = await db.get(AgentTask, task_id)
                assert abandoned.status == "retrying"
                assert abandoned.next_attempt_at > utc_now()
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_worker_executes_releases_and_retries_transient_failure(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                task = await agent_service.create_task(db, _task(order_id, "worker-success"))
            gateway = FakeAgentGateway({"customer_reception": FakeResult(
                "succeeded", {"needs_summary": "ok", "material_reminders": [],
                              "follow_up_questions": []})})
            assert await run_once(sessions, gateway)
            async with sessions() as db:
                finished = await db.get(AgentTask, task.id)
                assert finished.status == "succeeded" and finished.lease_owner is None
                workers = (await db.scalars(select(WorkerInstance))).all()
                assert len(workers) == 1 and workers[0].status == "stopped"
                failed = await agent_service.create_task(db, _task(order_id, "worker-rate-limit"))

            class RateLimited:
                async def invoke(self, _request):
                    raise ModelRateLimitError("provider details must stay private")

            assert await run_once(sessions, RateLimited())
            async with sessions() as db:
                retried = await db.get(AgentTask, failed.id)
                assert retried.status == "retrying" and retried.attempt_count == 1
                assert retried.next_attempt_at > utc_now()
                assert "provider details" not in retried.error_message
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)
