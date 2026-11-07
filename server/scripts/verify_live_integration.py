"""Opt-in, billable MiMo validation through the live HTTP API and standalone Worker."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]


async def verify(args):
    async with httpx.AsyncClient(base_url=args.url, timeout=60, follow_redirects=True) as client:
        customer = {"X-User-Id": "live-verification"}
        owner = {"X-User-Id": "owner"}

        async def call(method, path, *, boss=False, **kw):
            r = await client.request(method, "/api/v1" + path, headers=owner if boss else customer, **kw)
            if r.is_error:
                raise RuntimeError(f"{method} {path}: HTTP {r.status_code} {r.text[:400]}")
            return r.json() if "json" in r.headers.get("content-type", "") else r.text

        if args.order_id:
            order_id = args.order_id
        else:
            studio = await call(
                "POST", "/studios", json={"name": "松石设计工作室", "business_type": "digital_services"}
            )
            order = await call(
                "POST",
                "/orders",
                json={
                    "studio_id": studio["id"],
                    "period_start": "2026-10-01",
                    "period_end": "2026-10-31",
                    "service_scope": "monthly_records",
                },
            )
            order_id = order["id"]
            fixtures = ROOT / "fixtures/mvp"
            for i in range(1, 7):
                await call(
                    "POST",
                    f"/orders/{order_id}/files",
                    data={"file_category": "invoice_image"},
                    files={
                        "files": (
                            f"receipt-{i:02}.png",
                            (fixtures / f"receipt-{i:02}.png").read_bytes(),
                            "image/png",
                        )
                    },
                )
            rows = list(
                csv.DictReader((fixtures / "statement.csv").read_text(encoding="utf-8-sig").splitlines())
            )
            text = "transaction_date,counterparty,direction,amount,description,external_id\n" + "".join(
                f"{r['date']},{r['counterparty']},OUT,{r['amount']},合成验证,{r['transaction_id']}\n"
                for r in rows
            )
            file = await call(
                "POST",
                f"/orders/{order_id}/files",
                data={"file_category": "bank_statement_csv"},
                files={"files": ("statement.csv", text.encode(), "text/csv")},
            )
            await call("POST", f"/orders/{order_id}/imports/csv", json={"file_id": file["files"][0]["id"]})
            order = await call("GET", f"/orders/{order_id}")
            await call(
                "POST",
                f"/orders/{order_id}/runs",
                json={"idempotency_key": str(uuid4()), "expected_revision": order["input_revision"]},
            )
        print(
            json.dumps(
                {
                    "order_id": order_id,
                    "validation": "real MiMo; synthetic materials and explicit simulated human review",
                }
            ),
            flush=True,
        )

        async def wait():
            previous = None
            for _ in range(900):
                run = await call("GET", f"/orders/{order_id}/runs/current")
                now = (run["status"], run["stage"], run["requests_used"])
                if now != previous:
                    print(json.dumps({"status": now[0], "stage": now[1], "requests": now[2]}), flush=True)
                    previous = now
                if run["status"] in {"paused", "succeeded"}:
                    return run
                if run["status"] == "failed":
                    detail = await call("GET", f"/orders/{order_id}/runs/current", boss=True)
                    raise RuntimeError(str(detail.get("error")))
                await asyncio.sleep(1)
            raise RuntimeError("Worker wait exceeded fifteen minutes")

        run = await wait()
        tickets = await call("GET", f"/orders/{order_id}/exceptions")
        assert len(tickets) == 3, tickets
        assert [t["difference_cents"] for t in tickets if t["exception_type"] == "AMOUNT_MISMATCH"] == [27000]
        batch = await call("GET", f"/orders/{order_id}/reconciliation")
        assert batch["matched_count"] == 4, batch
        # Only synthetic fixtures. No approval is delegated to an Agent.
        mismatch = next(t for t in tickets if t["exception_type"] == "AMOUNT_MISMATCH")
        if mismatch["status"] == "open" and not args.skip_supplement:
            await call(
                "POST",
                f"/exceptions/{mismatch['id']}/decisions",
                boss=True,
                json={
                    "decision": "request_supplement",
                    "reason": "合成验证：请补充差额凭证",
                    "target_version": 1,
                },
            )
            await wait()
        fresh_tickets = await call("GET", f"/orders/{order_id}/exceptions")
        mismatch = next(t for t in fresh_tickets if t["exception_type"] == "AMOUNT_MISMATCH")
        if mismatch["status"] == "waiting_customer" and not args.skip_supplement:
            await call(
                "POST",
                f"/exceptions/{mismatch['id']}/supplements",
                data={"explanation": "合成验证：可能是运费，暂无凭证，请继续保留差异。"},
            )
            await wait()
        tickets = await call("GET", f"/orders/{order_id}/exceptions")
        dashboard = await call("GET", "/owner/dashboard", boss=True, params={"order_id": order_id})
        target = dashboard["next_report_version"]
        for ticket in tickets:
            if ticket["status"] not in {"resolved", "accepted_unresolved"}:
                await call(
                    "POST",
                    f"/exceptions/{ticket['id']}/decisions",
                    boss=True,
                    json={
                        "decision": "accept_unresolved",
                        "reason": "合成验证：保留未解决事项，不核销差额。",
                        "target_version": target,
                    },
                )
        run = await wait()
        reports = await call("GET", f"/orders/{order_id}/reports", boss=True)
        report = reports[-1]
        customer_reports = await call("GET", f"/orders/{order_id}/reports")
        assert not customer_reports, customer_reports
        for action in ("submit-review", "approve", "publish"):
            if action == "submit-review" and report["status"] != "draft":
                continue
            if action == "approve" and report["status"] not in {"draft", "in_review"}:
                continue
            report = await call(
                "POST",
                f"/reports/{report['id']}/{action}",
                boss=True,
                json={"reason": "合成验证：人工确认本版本并保留全部异常"},
            )
        run = await wait()
        assert run["status"] == "succeeded", run
        assert report["unresolved_items"], report
        await call("GET", f"/reports/{report['id']}/download")
        trace = {}
        for role in (
            "supervisor",
            "invoice_processing",
            "data_reconciliation",
            "customer_reception",
            "risk_delivery",
        ):
            t = await call("GET", f"/owner/agents/{role}/trace", boss=True, params={"order_id": order_id})
            trace[role] = {
                "tasks": len(t["tasks"]),
                "delegations": len(t["delegations"]),
                "tools": sorted({r["tool"] for d in t["delegations"] for r in d["receipts"]}),
            }
        supervisor_trace = await call(
            "GET", "/owner/agents/supervisor/trace", boss=True, params={"order_id": order_id}
        )
        decisions = supervisor_trace.get("decisions", [])
        actions = {
            "delegated": "delegate_tasks",
            "waiting_owner": "request_owner_review",
            "waiting_customer": "wait_for_customer",
            "completed": "complete_workflow",
        }
        trace["supervisor"]["tools"] = sorted(
            {actions[d["action"]] for d in decisions if d["action"] in actions}
        )
        trace["supervisor"]["decision_count"] = len(decisions)
        trace["supervisor"]["delegated_tasks"] = sum(len(d.get("delegation_ids", [])) for d in decisions)
        summary = {
            "verified_at": datetime.now(UTC).isoformat(),
            "provider": "real MiMo",
            "models": ["mimo-v2.6-pro", "mimo-v2.6-flash"],
            "materials": "six synthetic invoice images and six payment rows",
            "human_review": "explicitly simulated by verification script for synthetic order only",
            "order_id": order_id,
            "requests_used": run["requests_used"],
            "matched_count": batch["matched_count"],
            "difference_cents": 27000,
            "exception_count": 3,
            "status": run["status"],
            "roles": trace,
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate-synthetic-review", action="store_true", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:3210")
    parser.add_argument("--order-id")
    parser.add_argument("--skip-supplement", action="store_true")
    parser.add_argument("--output", default="data/live-verification.json")
    asyncio.run(verify(parser.parse_args()))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "server"))
    main()
