import hashlib
import hmac
import json

from test_stage2 import create_order, exercise
from test_stage6 import create_report_draft, make_batch_with_exception

SECRET = "test-sandbox-webhook-secret-32-chars-long"


def test_sandbox_payment_idempotency_signature_refunds_and_tenant(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        path = f"/api/v1/orders/{order_id}/payments"
        headers = {"X-User-Id": "alice", "Idempotency-Key": "pay-1"}
        first = await client.post(path, headers=headers)
        assert first.status_code == 201, first.text
        intent = first.json()
        assert intent["amount_cents"] == 2599 and intent["currency"] == "CNY"
        assert intent["provider"] == "sandbox" and intent["status"] == "pending"
        assert (await client.post(path, headers=headers)).json()["id"] == intent["id"]
        assert (await client.post(path, headers={**headers, "Idempotency-Key": "pay-2"})).status_code == 409
        assert (await client.get(path, headers={"X-User-Id": "bob"})).status_code == 404

        async def callback(event_id, event_type, amount=None, *, valid=True):
            payload = {"event_id": event_id, "intent_id": intent["id"], "event_type": event_type,
                       "amount_cents": amount}
            raw = json.dumps(payload, separators=(",", ":")).encode()
            signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
            return await client.post("/api/v1/payments/sandbox/webhook", content=raw,
                                     headers={"X-Sandbox-Signature": signature if valid else "bad"})

        assert (await callback("evt-bad", "succeeded", 2599, valid=False)).status_code == 401
        assert (await callback("evt-mismatch", "succeeded", 1)).status_code == 409
        succeeded = await callback("evt-paid", "succeeded", 2599)
        assert succeeded.status_code == 200 and succeeded.json()["status"] == "succeeded"
        assert (await callback("evt-paid", "succeeded", 2599)).status_code == 200
        assert (await callback("evt-paid", "failed")).status_code == 409
        partial = await callback("evt-refund-1", "refunded", 999)
        assert partial.status_code == 200 and partial.json()["status"] == "partially_refunded"
        assert partial.json()["refunded_cents"] == 999
        assert (await callback("evt-over", "refunded", 1601)).status_code == 409
        full = await callback("evt-refund-2", "refunded", 1600)
        assert full.status_code == 200 and full.json()["status"] == "refunded"
        assert (await client.get(path, headers={"X-User-Id": "alice"})).json()[0]["id"] == intent["id"]

    exercise(tmp_path, monkeypatch, scenario, service_prices_cents='{"monthly_records":2599}',
             service_currency="CNY", payment_sandbox_webhook_secret=SECRET)


def test_payment_requires_explicit_pricing_and_webhook_secret(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        response = await client.post(f"/api/v1/orders/{order_id}/payments",
                                     headers={"X-User-Id": "alice", "Idempotency-Key": "pay-1"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "pricing_unconfigured"
        webhook = await client.post("/api/v1/payments/sandbox/webhook", content=b"{}",
                                    headers={"X-Sandbox-Signature": "bad"})
        assert webhook.status_code == 503
        assert webhook.json()["error"]["code"] == "payment_unavailable"

    exercise(tmp_path, monkeypatch, scenario)


def test_priced_report_requires_successful_payment_before_delivery(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        batch, ticket, match = await make_batch_with_exception(client, order_id)
        report = await create_report_draft(order_id, batch, ticket, match, 1, "Paid report")
        report_path = f"/api/v1/reports/{report.id}"
        assert (await client.post(f"{report_path}/submit-review", headers={"X-User-Id": "owner"})).status_code == 200
        assert (await client.post(f"{report_path}/approve", headers={"X-User-Id": "owner"})).status_code == 200
        blocked = await client.post(f"{report_path}/publish", headers={"X-User-Id": "owner"})
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "payment_required"
        assert (await client.get(f"/api/v1/orders/{order_id}", headers={"X-User-Id": "alice"})).json()["status"] == "approved"
        assert (await client.get(report_path, headers={"X-User-Id": "owner"})).json()["status"] == "approved"

        payment = await client.post(f"/api/v1/orders/{order_id}/payments",
                                    headers={"X-User-Id": "alice", "Idempotency-Key": "deliver-1"})
        assert payment.status_code == 201
        raw = json.dumps({"event_id": "deliver-paid", "intent_id": payment.json()["id"],
                          "event_type": "succeeded", "amount_cents": 2599}, separators=(",", ":")).encode()
        signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        assert (await client.post("/api/v1/payments/sandbox/webhook", content=raw,
                                  headers={"X-Sandbox-Signature": signature})).status_code == 200
        assert (await client.post(f"{report_path}/publish", headers={"X-User-Id": "owner"})).status_code == 200
        assert (await client.get(f"/api/v1/orders/{order_id}", headers={"X-User-Id": "alice"})).json()["status"] == "delivered"

    exercise(tmp_path, monkeypatch, scenario, service_prices_cents='{"monthly_records":2599}',
             service_currency="CNY", payment_sandbox_webhook_secret=SECRET)
