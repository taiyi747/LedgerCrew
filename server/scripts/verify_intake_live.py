"""Explicit billable intake precheck + existing supervised delivery validation."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from verify_live_integration import verify

ROOT = Path(__file__).resolve().parents[2]


async def main(args):
    async with httpx.AsyncClient(
        base_url=args.url, timeout=60, follow_redirects=True, headers={"X-User-Id": "live-verification"}
    ) as c:

        async def call(method, path, **kw):
            r = await c.request(method, "/api/v1" + path, **kw)
            if r.is_error:
                raise RuntimeError(f"{method} {path}: HTTP {r.status_code}: {r.text[:300]}")
            return r.json()

        if args.intake_id:
            intake = await call("GET", "/intakes/" + args.intake_id)
            iid = intake["id"]
        else:
            intake = await call("POST", "/intakes", json={})
            iid = intake["id"]
            print(
                json.dumps(
                    {
                        "intake_id": iid,
                        "mode": "real MiMo, synthetic materials, explicit simulated customer confirmation",
                    }
                ),
                flush=True,
            )
            intake = await call(
                "PATCH",
                f"/intakes/{iid}",
                json={
                    "expected_revision": intake["revision"],
                    "studio_name": "松石设计工作室",
                    "period_start": "2026-10-01",
                    "period_end": "2026-10-31",
                },
            )
            intake = await call(
                "POST",
                f"/intakes/{iid}/files",
                data={"expected_revision": intake["revision"]},
                files={
                    "files": (
                        "materials.zip",
                        (ROOT / "fixtures/mvp/materials.zip").read_bytes(),
                        "application/zip",
                    )
                },
            )
        job = await call("POST", f"/intakes/{iid}/prechecks", json={"expected_revision": intake["revision"]})
        previous = None
        for _ in range(420):
            intake = await call("GET", f"/intakes/{iid}")
            progress = (intake["status"], intake["precheck"]["requests_used"])
            if progress != previous:
                print(json.dumps({"status": progress[0], "precheck_requests": progress[1]}), flush=True)
                previous = progress
            if intake["precheck"]["status"] == "failed":
                raise RuntimeError("Real intake precheck failed; inspect owner snapshot and local logs")
            if intake["precheck"]["status"] == "succeeded":
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Precheck exceeded seven minutes")
        if not intake["confirmation"]:
            raise RuntimeError(json.dumps(intake["precheck"]["result"]["blockers"], ensure_ascii=False))
        assert intake["order_id"] is None
        result = intake["precheck"]["result"]
        assert len(result["sampled_file_ids"]) == 3
        if args.preview_only:
            record = {
                "verified_at": datetime.now(UTC).isoformat(),
                "provider": "real MiMo Flash",
                "intake_id": iid,
                "status": intake["status"],
                "precheck_requests": intake["precheck"]["requests_used"],
                "request_limit": intake["precheck"]["request_limit"],
                "sampled_images": len(result["sampled_file_ids"]),
                "order_created": False,
                "summary": result["narrative"]["summary"],
            }
            (ROOT / "docs/verification/intake-precheck-live.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(record, ensure_ascii=False), flush=True)
            return
        payload = {
            "expected_revision": intake["revision"],
            "precheck_id": job["id"],
            "service_version": intake["service"]["version"],
            "idempotency_key": str(uuid4()),
            "acknowledged_warning_ids": [w["id"] for w in result["warnings"]],
        }
        order = await call("POST", f"/intakes/{iid}/confirm", json=payload)
        assert await call("POST", f"/intakes/{iid}/confirm", json=payload) == order
        assert order["price_cents"] == 1990
        print(
            json.dumps(
                {"order_id": order["order_id"], "precheck_requests": intake["precheck"]["requests_used"]}
            ),
            flush=True,
        )
        summary = {
            "verified_at": datetime.now(UTC).isoformat(),
            "provider": "real MiMo Flash",
            "intake_id": iid,
            "order_id": order["order_id"],
            "status": "confirmed",
            "precheck_requests": intake["precheck"]["requests_used"],
            "precheck_limit": intake["precheck"]["request_limit"],
            "sampled_images": len(result["sampled_file_ids"]),
            "price_cents": order["price_cents"],
            "materials": "six synthetic invoice images and canonical CSV in a mixed ZIP",
            "human_actions": "explicitly simulated customer profile, warning acknowledgments and order confirmation",
            "precheck_summary": result["narrative"]["summary"],
            "warning_codes": [w["code"] for w in result["warnings"]],
        }
        output = ROOT / "docs/verification/intake-live.json"
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.precheck_only:
        await verify(
            SimpleNamespace(
                url=args.url,
                order_id=order["order_id"],
                skip_supplement=False,
                output=str(ROOT / "docs/verification/intake-delivery-live.json"),
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate-synthetic-review", action="store_true", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:3210")
    parser.add_argument("--precheck-only", action="store_true")
    parser.add_argument("--preview-only", action="store_true", help="仅预检，不确认或启动正式订单")
    parser.add_argument("--intake-id", help="继续本客户已存在的合成验证会话")
    asyncio.run(main(parser.parse_args()))
