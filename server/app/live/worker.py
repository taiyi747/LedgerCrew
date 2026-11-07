from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import update

from app.agents.config import Settings
from app.agents.errors import AgentError
from app.agents.runner import MiMoRunner
from app.db.session import SessionLocal
from app.db.types import utc_now
from app.live import service
from app.live.contracts import WorkflowWake
from app.live.engine import LiveRuntime, checkpoint_storage, production_workflow
from app.live.models import OrderMessage, WorkflowRun
from app.models import Order

DATA = Path(
    os.environ.get("LEDGERCREW_LIVE_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data" / "live"))
)


async def execute_run(sessions, run_id, token, *, runner=None, data_dir=None, raise_errors=False):
    path = (data_dir or DATA) / "checkpoints" / run_id
    storage = checkpoint_storage(path)
    runtime = LiveRuntime(sessions, run_id, token, runner=runner)
    workflow = production_workflow(runtime, storage)

    async def heartbeat():
        while True:
            await asyncio.sleep(5)
            async with sessions() as session:
                result = await session.execute(
                    update(WorkflowRun)
                    .where(
                        WorkflowRun.id == run_id,
                        WorkflowRun.lease_token == token,
                        WorkflowRun.status == "running",
                    )
                    .values(heartbeat_at=utc_now(), lease_expires_at=utc_now() + timedelta(seconds=60))
                )
                await session.commit()
                if result.rowcount == 0:
                    return

    pulse = asyncio.create_task(heartbeat())
    try:
        async with sessions() as session:
            run = await session.get(WorkflowRun, run_id)
            saved_checkpoint, pending = run.checkpoint_id, run.pending_request_id
        # A crash may precede writing the checkpoint pointer to SQL.
        latest = await storage.get_latest(workflow_name="live-" + run_id)
        if saved_checkpoint:
            responses = {pending: WorkflowWake(run_id=run_id)} if pending else None
            try:
                result = await workflow.run(checkpoint_id=saved_checkpoint, responses=responses)
            except RuntimeError as error:
                if not responses or str(error) != "No pending requests found in workflow context.":
                    raise
                # A failed resumed step may save a newer checkpoint after consuming the old request.
                workflow = production_workflow(runtime, storage)
                result = await workflow.run(checkpoint_id=saved_checkpoint)
        elif latest:
            result = await workflow.run(checkpoint_id=latest.checkpoint_id)
        else:
            result = await workflow.run(run_id)
        checkpoint = await storage.get_latest(workflow_name="live-" + run_id)
        requests = result.get_request_info_events()
        async with sessions() as session:
            run = await session.get(WorkflowRun, run_id)
            if run.lease_token != token:
                return
            run.checkpoint_id = checkpoint.checkpoint_id if checkpoint else None
            run.pending_request_id = requests[0].request_id if requests else None
            if requests:
                # Publish the wait and checkpoint pointer atomically before accepting human input.
                run.status = "paused"
            run.lease_token = run.lease_expires_at = None
            await session.commit()
    except Exception as error:
        async with sessions() as session:
            run = await session.get(WorkflowRun, run_id)
            if run and run.lease_token == token:
                safe = str(error) if isinstance(error, AgentError) else type(error).__name__
                run.status, run.error = "failed", safe
                run.lease_token = run.lease_expires_at = None
                if run.kind == "processing":
                    order = await session.get(Order, run.order_id)
                    if order.status != "delivered":
                        order.status = "failed"
                else:
                    session.add(
                        OrderMessage(
                            order_id=run.order_id,
                            workflow_run_id=run.id,
                            role="assistant",
                            content="本次服务未能完成，请重试或联系老板检查配置。",
                            status="failed",
                            input_revision=run.input_revision,
                        )
                    )
                checkpoint = await storage.get_latest(workflow_name="live-" + run_id)
                if checkpoint:
                    run.checkpoint_id = checkpoint.checkpoint_id
                    run.pending_request_id = None
                await service.event(session, run.order_id, "workflow.failed", {"workflow_run_id": run.id})
                await session.commit()
        if raise_errors:
            raise
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)


async def worker(*, once=False):
    settings = Settings.from_env()
    runner = MiMoRunner(settings, request_semaphore=asyncio.Semaphore(2))
    DATA.mkdir(parents=True, exist_ok=True)
    active = {}
    try:
        while True:
            (DATA / "heartbeat.json").write_text(
                json.dumps({"pid": os.getpid(), "at": utc_now().isoformat()}), encoding="utf-8"
            )
            for kind in ("processing", "chat"):
                if kind in active and active[kind].done():
                    await active.pop(kind)
                if kind not in active:
                    token = str(uuid4())
                    async with SessionLocal() as session:
                        run_id = await service.claim_run(session, kind, token)
                    if run_id:
                        active[kind] = asyncio.create_task(
                            execute_run(SessionLocal, run_id, token, runner=runner)
                        )
            if once:
                await asyncio.gather(*active.values())
                return
            await asyncio.sleep(0.4)
    finally:
        for task in active.values():
            task.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description="LedgerCrew 实时总管与专业 Agent Worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(worker(once=args.once))


if __name__ == "__main__":
    main()
