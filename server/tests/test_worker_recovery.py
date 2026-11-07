from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise

from app.core.config import get_settings
from app.db.session import make_engine
from app.db.types import utc_now
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service


def test_worker_cancel_retry_limit_timeout_and_history(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                cancelled = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="cancel-me", correlation_id="worker-flow",
                    input_payload={"order_id": order_id, "customer_message": "Cancel"}))
                retrying = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="retry-me", correlation_id="worker-flow",
                    input_payload={"order_id": order_id, "customer_message": "Retry"}))
                stale = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="timeout-me", correlation_id="worker-flow",
                    input_payload={"order_id": order_id, "customer_message": "Timeout"}))
                await agent_service.start_task(db, retrying.id)
                await agent_service.fail_task(db, retrying.id, "temporary_error")
                await agent_service.start_task(db, stale.id)
                stale.started_at = utc_now() - timedelta(hours=1)
                await db.commit()
                expired = await agent_service.timeout_stale_tasks(db)
                assert [task.id for task in expired] == [stale.id]
                assert expired[0].status == "timeout"
        finally:
            await engine.dispose()

        cancel_url = f"/api/v1/agent-tasks/{cancelled.id}"
        assert (await client.post(f"{cancel_url}/cancel", headers={"X-User-Id": "alice"})).status_code == 403
        assert (await client.post(f"{cancel_url}/cancel", headers={"X-User-Id": "owner"})).json()["status"] == "cancelled"
        assert (await client.post(f"{cancel_url}/cancel", headers={"X-User-Id": "owner"})).json()["status"] == "cancelled"
        assert (await client.post(f"{cancel_url}/retry", headers={"X-User-Id": "owner"})).status_code == 409
        retry_url = f"/api/v1/agent-tasks/{retrying.id}"
        assert (await client.post(f"{retry_url}/retry", headers={"X-User-Id": "owner"})).json()["status"] == "retrying"
        history = (await client.get(f"{retry_url}/history", headers={"X-User-Id": "owner"})).json()
        assert [row["to_status"] for row in history] == ["queued", "running", "failed", "retrying"]
        assert history[2]["reason"] == "temporary_error"
        assert (await client.post(f"/api/v1/agent-tasks/{stale.id}/retry",
                                  headers={"X-User-Id": "owner"})).json()["status"] == "retrying"

        engine = make_engine(get_settings().database_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                await agent_service.start_task(db, retrying.id)
                await agent_service.fail_task(db, retrying.id, "second_failure")
        finally:
            await engine.dispose()
        limited = await client.post(f"{retry_url}/retry", headers={"X-User-Id": "owner"})
        assert limited.status_code == 409 and limited.json()["error"]["code"] == "retry_limit"

    exercise(tmp_path, monkeypatch, scenario, worker_max_attempts=2, worker_timeout_seconds=30)
