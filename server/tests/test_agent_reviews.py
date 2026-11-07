from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise

from app.core.config import get_settings
from app.db.session import make_engine
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service


def test_agent_result_review_correction_rejection_and_rerun(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                first = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="review-1", correlation_id="review-flow",
                    input_payload={"order_id": order_id, "customer_message": "Hello"}))
                await agent_service.start_task(db, first.id)
                await agent_service.complete_task(db, first.id, {"needs_summary": "Original"})
                second = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="review-2", correlation_id="review-flow",
                    input_payload={"order_id": order_id, "customer_message": "Again"}))
                await agent_service.start_task(db, second.id)
                await agent_service.complete_task(db, second.id, {"needs_summary": "Wrong"})
        finally:
            await engine.dispose()

        path = f"/api/v1/agent-tasks/{first.id}/reviews"
        assert (await client.get(path, headers={"X-User-Id": "alice"})).status_code == 403
        confirmed = await client.post(path, json={"decision": "confirmed", "note": "Checked"},
                                      headers={"X-User-Id": "owner"})
        assert confirmed.status_code == 201 and confirmed.json()["version"] == 1
        corrected = await client.post(path, json={"decision": "corrected", "note": "Fixed wording",
                                                  "revised_output": {"needs_summary": "Corrected"}},
                                      headers={"X-User-Id": "owner"})
        assert corrected.status_code == 201 and corrected.json()["version"] == 2
        assert corrected.json()["original_output"]["needs_summary"] == "Original"
        assert corrected.json()["revised_output"]["needs_summary"] == "Corrected"
        assert len((await client.get(path, headers={"X-User-Id": "owner"})).json()) == 2
        rejected = await client.post(f"/api/v1/agent-tasks/{second.id}/reviews",
                                     json={"decision": "rejected", "note": "Incorrect analysis"},
                                     headers={"X-User-Id": "owner"})
        assert rejected.status_code == 201
        assert (await client.post(f"/api/v1/agent-tasks/{second.id}/reviews",
                                  json={"decision": "confirmed", "note": "No"},
                                  headers={"X-User-Id": "owner"})).status_code == 409
        rerun = await client.post(f"/api/v1/agent-tasks/{second.id}/rerun",
                                  headers={"X-User-Id": "owner", "Idempotency-Key": "rerun-2"})
        assert rerun.status_code == 201 and rerun.json()["status"] == "queued"
        assert rerun.json()["id"] != second.id
        assert (await client.post(f"/api/v1/agent-tasks/{second.id}/rerun",
                                  headers={"X-User-Id": "owner", "Idempotency-Key": "rerun-2"})).json()["id"] == rerun.json()["id"]
        stats = await client.get(f"/api/v1/orders/{order_id}/agent-reviews/stats",
                                 headers={"X-User-Id": "owner"})
        assert stats.json() == {"confirmed": 1, "corrected": 1, "rejected": 1, "reviewed_tasks": 2}

    exercise(tmp_path, monkeypatch, scenario)
