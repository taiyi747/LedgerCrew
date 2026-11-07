"""Explicit, billable live check of the persisted backend MiMo task chain."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker

from alembic import command
from app.agents.config import Settings as MiMoSettings
from app.agents.contracts import RunIdentity
from app.core.config import get_settings
from app.db.session import make_engine
from app.integrations.agents.mimo_gateway import MiMoAgentGateway, TaskModelArtifacts
from app.models import AgentTask, Order, Studio
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service
from app.storage.local import LocalStorage
from scripts.run_agent_tasks import run_once


async def verify(db_path: Path, settings: MiMoSettings) -> dict:
    engine = make_engine(get_settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            studio = Studio(name="Synthetic backend MiMo smoke test", owner_user_id="live-operator")
            db.add(studio)
            await db.flush()
            order = Order(studio_id=studio.id, order_no="LIVE-" + uuid4().hex,
                          period_start=date(2026, 10, 1), period_end=date(2026, 10, 31),
                          period_year=2026, period_month=10, status="ready_to_process",
                          is_simulated=True)
            db.add(order)
            await db.commit()
            task = await agent_service.create_task(db, AgentTaskCreate(
                order_id=order.id, agent_role="customer_reception", task_type="customer_reception",
                idempotency_key="live-" + uuid4().hex, correlation_id="backend-live-check",
                input_payload={"order_id": order.id,
                               "customer_message": "合成测试：请概括需要收集哪些月度材料。"}))
        gateway = MiMoAgentGateway(sessions, LocalStorage(str(db_path.parent / "storage")), settings)
        await run_once(sessions, gateway)
        async with sessions() as db:
            stored = await db.get(AgentTask, task.id)
            identity = TaskModelArtifacts(sessions, task.id)
            run_identity = RunIdentity(order_id=order.id, run_id=task.run_id, revision=1)
            usage = await identity.load_artifact(run_identity, "usage")
            settlement = await identity.load_artifact(run_identity, "model_settlement")
            result = {"task_id": task.id, "status": stored.status,
                      "model": (stored.provider_metadata or {}).get("model"),
                      "elapsed_ms": (stored.provider_metadata or {}).get("elapsed_ms"),
                      "request_count": (usage or {}).get("requests", 0),
                      "usage_status": (settlement or {}).get("usage_status", "unknown"),
                      "http_status": (settlement or {}).get("http_status"),
                      "database": str(db_path)}
            if stored.status != "succeeded" or result["request_count"] == 0 or settlement is None:
                raise RuntimeError(json.dumps(result, ensure_ascii=False))
            return result
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit live backend MiMo verification")
    parser.add_argument("--run-live", action="store_true", required=True)
    args = parser.parse_args()
    if not args.run_live or os.environ.get("LEDGERCREW_ENABLE_LIVE_MIMO") != "1":
        parser.error("Set LEDGERCREW_ENABLE_LIVE_MIMO=1 and pass --run-live")
    settings = MiMoSettings.from_env()  # Refuses missing or placeholder credentials.
    root = Path(__file__).resolve().parents[1] / "data" / "live-backend"
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / ("mimo-" + uuid4().hex + ".db")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + db_path.as_posix()
    get_settings.cache_clear()
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    result = asyncio.run(verify(db_path, settings))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
