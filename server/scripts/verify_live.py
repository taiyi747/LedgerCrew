"""Explicit, billable live test. Human replies are simulated for synthetic data only."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="真实 MiMo＋合成样例的跨进程验证")
    parser.add_argument(
        "--simulate-human-review",
        action="store_true",
        required=True,
        help="明确允许验证脚本模拟合成订单的人工决定；不用于客户订单",
    )
    args = parser.parse_args()
    if not args.simulate_human_review:
        return
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    relative_data = "data/live-" + uuid.uuid4().hex[:12]
    environment["LEDGERCREW_DATA_DIR"] = relative_data
    steps = []

    def call(*arguments):
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "app.agents.cli", *arguments],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        if completed.returncode:
            try:
                error = json.loads(completed.stdout).get("error", "验证失败")
            except (ValueError, AttributeError):
                error = "子进程失败；请检查本地运行记录。"
            raise RuntimeError(f"{arguments[0]}: {error}")
        result = json.loads(completed.stdout)
        steps.append(
            {
                "command": arguments[0],
                "requests": result.get("usage", {}).get("requests"),
                "pending_kinds": [item["request"]["kind"] for item in result.get("pending", [])],
            }
        )
        print(json.dumps(steps[-1], ensure_ascii=False), flush=True)
        return result

    first = call("start")
    assert first["pending"][0]["request"]["kind"] == "exception"
    pending = call(
        "resume",
        "--request-id",
        first["pending"][0]["request_id"],
        "--action",
        "request_info",
        "--comment",
        "测试操作者：请提供差额依据和缺失票据。",
    )
    assert pending["pending"][0]["request"]["kind"] == "customer"
    updated = call(
        "supplement",
        "--request-id",
        pending["pending"][0]["request_id"],
        "--comment",
        "合成客户说明：差额可能为运费，暂无凭证；缺票仍待补充。",
    )
    assert updated["pending"][0]["request"]["identity"]["revision"] == 2
    drafted = call(
        "resume",
        "--request-id",
        updated["pending"][0]["request_id"],
        "--action",
        "keep_flagged",
        "--comment",
        "测试操作者：保留全部异常，交付待核实清单。",
    )
    review = drafted["pending"][0]["request"]
    assert review["kind"] == "delivery"
    approved = call(
        "resume",
        "--request-id",
        review["request_id"],
        "--action",
        "approve_delivery",
        "--report-version",
        str(review["report_version"]),
    )
    output = approved["outputs"][0]
    assert output["status"] == "delivery_approved"
    reconciliation = output["report"]["reconciliation"]
    assert len(reconciliation["matches"]) == 4
    issues = reconciliation["issues"]
    assert [i["difference_minor"] for i in issues if i["kind"] == "amount_mismatch"] == [27000]
    assert sum(i["kind"] == "duplicate" for i in issues) == 1
    assert sum(i["kind"] == "missing_invoice" for i in issues) == 1
    assert len(output["report"]["unresolved_issue_ids"]) == 3
    repeated = call(
        "resume",
        "--request-id",
        review["request_id"],
        "--action",
        "approve_delivery",
        "--report-version",
        str(review["report_version"]),
    )
    assert repeated.get("replayed") is True
    assert repeated["usage"] == approved["usage"]
    summary = {
        "status": "passed",
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "framework_core": importlib.metadata.version("agent-framework-core"),
        "framework_openai": importlib.metadata.version("agent-framework-openai"),
        "models": {"pro": "mimo-v2.6-pro", "flash": "mimo-v2.6-flash"},
        "synthetic_data": True,
        "human_decisions": "explicitly simulated test operator",
        "backend": "fixture-only reference reconciliation, not production backend",
        "fresh_python_processes": len(steps),
        "matched_count": 4,
        "amount_difference_minor": 27000,
        "duplicate_count": 1,
        "missing_invoice_count": 1,
        "unresolved_issues_preserved": 3,
        "final_input_revision": 2,
        "report_version": review["report_version"],
        "requests": approved["usage"]["requests"],
        "duplicate_approval_replayed_without_model_request": True,
        "steps": steps,
    }
    result_path = root / "server" / relative_data / "verification.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "local_record": str(result_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
