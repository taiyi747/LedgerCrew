"""Explicit real-MiMo check of ReAct planning and non-template CSV normalization."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx


async def verify(args):
    async with httpx.AsyncClient(
        base_url=args.url, headers={"X-User-Id": "workspace-verification"}, timeout=30
    ) as client:

        async def call(method, path, **values):
            response = await client.request(method, "/api/v1" + path, **values)
            response.raise_for_status()
            return response.json()

        if args.intake_id:
            item = await call("GET", "/intakes/" + args.intake_id)
        else:
            item = await call("POST", "/intakes", json={})
        iid = item["id"]
        if not args.intake_id:
            item = await call(
                "PATCH",
                f"/intakes/{iid}",
                json={
                    "expected_revision": item["revision"],
                    "studio_name": "青禾工作区合成验证",
                    "period_start": "2025-10-01",
                    "period_end": "2025-10-31",
                },
            )
        content = "交易日期,对方户名,收支,发生额\n2025/10/16,杭州合成供应商,支出,2850.00\n".encode(
            "utf-8-sig"
        )
        if not args.intake_id:
            item = await call(
                "POST",
                f"/intakes/{iid}/files",
                data={"expected_revision": item["revision"]},
                files={"files": ("原始银行导出.csv", content, "text/csv")},
            )
        await call("POST", f"/intakes/{iid}/prechecks", json={"expected_revision": item["revision"]})
        print(
            json.dumps({"intake_id": iid, "mode": "real MiMo, synthetic one-row source, no order creation"}),
            flush=True,
        )
        for _ in range(240):
            item = await call("GET", f"/intakes/{iid}")
            if item["precheck"]["status"] in {"succeeded", "failed"}:
                break
            await asyncio.sleep(1)
        check = item["precheck"]
        print(
            json.dumps(
                {"status": check["status"], "requests": check["requests_used"], "todos": check["todos"]},
                ensure_ascii=False,
            ),
            flush=True,
        )
        assert check["status"] == "succeeded", check["error"]
        derived = [file for file in item["files"] if file["derived_from_file_id"] and file["included"]]
        assert derived and item["confirmation"] and not item["order_id"]
        assert all(todo["status"] == "completed" for todo in check["todos"])
        response = await client.get(f"/api/v1/intakes/{iid}/files/{derived[0]['id']}/download")
        response.raise_for_status()
        assert "2850.00" in response.content.decode("utf-8-sig")
        record = {
            "verified_at": datetime.now(UTC).isoformat(),
            "mode": "real MiMo",
            "materials": "one synthetic CSV with original Chinese headers",
            "status": check["status"],
            "requests_used": check["requests_used"],
            "todos": [{"title": todo["title"], "status": todo["status"]} for todo in check["todos"]],
            "derived_files": len(derived),
            "verified_amount_cents": 285000,
            "order_created": False,
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Verified ReAct tool results and traceable normalized source.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-live", action="store_true", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--intake-id")
    parser.add_argument("--output", default="../docs/verification/react-intake-live.json")
    asyncio.run(verify(parser.parse_args()))
