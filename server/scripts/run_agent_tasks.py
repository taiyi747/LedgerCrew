"""Single-process backend task executor; deploy one instance with SQLite."""

import argparse
import asyncio
import logging
import signal
from contextlib import suppress
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import Settings as MiMoSettings
from app.core.config import get_settings
from app.db.session import make_engine
from app.integrations.agents.gateway import AgentGateway
from app.integrations.agents.mimo_gateway import MiMoAgentGateway
from app.integrations.agents.workflow_gateway import FullWorkflowGateway, RoutedAgentGateway
from app.services import agent_service, worker_service
from app.storage.local import get_storage

logger = logging.getLogger(__name__)


async def run_once(sessions: async_sessionmaker[AsyncSession], gateway: AgentGateway,
                   worker_id: str | None = None,
                   stop_event: asyncio.Event | None = None) -> bool:
    owns_worker = worker_id is None
    if owns_worker:
        async with sessions() as db:
            worker_id = (await worker_service.register(db)).id
    async with sessions() as db:
        claimed = await worker_service.claim_next(db, worker_id)
    if claimed is None:
        if owns_worker:
            async with sessions() as db:
                await worker_service.stop(db, worker_id)
        return False
    task_id, generation = claimed
    execution = asyncio.current_task()

    async def renew() -> None:
        while True:
            await asyncio.sleep(get_settings().worker_heartbeat_seconds)
            async with sessions() as db:
                if not await worker_service.heartbeat(db, worker_id, task_id, generation):
                    execution.cancel()
                    return

    keepalive = asyncio.create_task(renew())
    async def stop_on_signal() -> None:
        if stop_event is not None:
            await stop_event.wait()
            execution.cancel()

    signal_watcher = asyncio.create_task(stop_on_signal()) if stop_event is not None else None
    try:
        async with sessions() as db:
            task = await agent_service.invoke_task(
                db, task_id, gateway, lease_owner=worker_id, lease_generation=generation)
            logger.info("Agent task %s ended with status %s", task.id, task.status)
            await worker_service.retry_if_transient(db, task_id)
        return True
    finally:
        keepalive.cancel()
        await asyncio.gather(keepalive, return_exceptions=True)
        if signal_watcher is not None:
            signal_watcher.cancel()
            await asyncio.gather(signal_watcher, return_exceptions=True)
        async with sessions() as db:
            await worker_service.abandon(db, worker_id, task_id, generation)
            await worker_service.release(db, worker_id, task_id, generation)
            if owns_worker:
                await worker_service.stop(db, worker_id)


async def run(poll_seconds: float, once: bool) -> None:
    settings = MiMoSettings.from_env()  # Fail before claiming tasks when the key is absent.
    backend = get_settings()
    if backend.worker_heartbeat_seconds * 2 >= backend.worker_lease_seconds:
        raise ValueError("Worker heartbeat must be less than half the lease duration")
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    storage = get_storage()
    gateway = RoutedAgentGateway(
        MiMoAgentGateway(sessions, storage, settings),
        FullWorkflowGateway(sessions, storage,
                            Path(backend.storage_root).resolve() / "workflow_checkpoints", settings))
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:  # Windows event loop
            signal.signal(signum, lambda _signal, _frame: stop_event.set())
    async with sessions() as db:
        worker_id = (await worker_service.register(db)).id
    try:
        while not stop_event.is_set():
            async with sessions() as db:
                await worker_service.recover_expired(db)
            handled = await run_once(sessions, gateway, worker_id, stop_event)
            if once:
                return
            if not handled:
                async with sessions() as db:
                    await worker_service.heartbeat(db, worker_id)
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
    finally:
        async with sessions() as db:
            await worker_service.stop(db, worker_id)
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backend Agent tasks through MiMo")
    parser.add_argument("--once", action="store_true", help="Process one queued task and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.poll_seconds, args.once))


if __name__ == "__main__":
    main()
