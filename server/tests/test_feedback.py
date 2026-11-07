from test_stage2 import create_order, exercise


def test_feedback_tenant_links_handling_and_history(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        studio_id, order_id = await create_order(client)
        path = f"/api/v1/studios/{studio_id}/feedback"
        body = {"category": "question", "message": "Please explain this order", "order_id": order_id}
        assert (await client.post(path, json=body, headers={"X-User-Id": "bob"})).status_code == 404
        created = await client.post(path, json=body, headers={"X-User-Id": "alice"})
        assert created.status_code == 201
        feedback_id = created.json()["id"]
        assert created.json()["status"] == "open"
        assert (await client.get(f"/api/v1/feedback/{feedback_id}", headers={"X-User-Id": "bob"})).status_code == 404
        assert len((await client.get(path, headers={"X-User-Id": "alice"})).json()) == 1
        action_path = f"/api/v1/feedback/{feedback_id}/actions"
        assert (await client.post(action_path, json={"action": "resolved", "note": "Answered"},
                                  headers={"X-User-Id": "alice"})).status_code == 403
        handled = await client.post(action_path, json={"action": "resolved", "note": "Answered"},
                                    headers={"X-User-Id": "owner"})
        assert handled.status_code == 200
        assert handled.json()["status"] == "resolved"
        assert handled.json()["handled_by"] == "owner" and handled.json()["handled_at"]
        actions = await client.get(action_path, headers={"X-User-Id": "alice"})
        assert actions.status_code == 200 and actions.json()[0]["note"] == "Answered"
        assert (await client.post(action_path, json={"action": "rejected", "note": "Late"},
                                  headers={"X-User-Id": "owner"})).status_code == 409

        other_studio, other_order = await create_order(client, user="bob")
        assert other_studio != studio_id
        foreign = await client.post(path, json={**body, "order_id": other_order},
                                    headers={"X-User-Id": "alice"})
        assert foreign.status_code == 404

    exercise(tmp_path, monkeypatch, scenario)
