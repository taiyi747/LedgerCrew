"""Generate visibly synthetic receipts and their expected answers for development."""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .contracts import FileRef, OrderInput, RunIdentity, Transaction

RECEIPTS = [
    ("receipt-01", "LC-DEMO-001", "2026-10-10", "青禾纸业", "108.00"),
    ("receipt-02", "LC-DEMO-002", "2026-10-11", "云杉文具", "36.90"),
    ("receipt-03", "LC-DEMO-003", "2026-10-12", "林间印务", "860.00"),
    ("receipt-04", "LC-DEMO-004", "2026-10-13", "启明网络", "450.00"),
    ("receipt-05", "LC-DEMO-005", "2026-10-14", "远山设备", "2580.00"),
]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_fixtures(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    fonts = [Path("C:/Windows/Fonts/msyh.ttc"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    font_path = next((p for p in fonts if p.exists()), None)
    font = ImageFont.truetype(str(font_path), 28) if font_path else ImageFont.load_default(size=28)
    expected = []
    for file_id, number, date_text, vendor, amount in RECEIPTS:
        image = Image.new("RGB", (1040, 660), "#fafaf8")
        draw = ImageDraw.Draw(image)
        draw.rectangle((24, 24, 1016, 636), outline="#294d43", width=3)
        lines = [
            "SYNTHETIC DEMO / 合成测试票据",
            "LedgerCrew 票据识别与对账样例",
            f"发票号码 Invoice number: {number}",
            f"开票日期 Date: {date_text}",
            f"销售方 Seller: {vendor}",
            "购买方 Buyer: 松石设计工作室",
            f"价税合计 Total (CNY): {amount}",
            "付款方向 Direction: 支出 out",
            "仅供软件测试，不具有真实发票效力。",
        ]
        for row, text in enumerate(lines):
            draw.text((55, 48 + row * 60), text, fill="#263a33", font=font)
        path = root / (file_id + ".png")
        image.save(path)
        expected.append(
            {
                "file_id": file_id,
                "invoice_number": number,
                "date": date_text,
                "counterparty": vendor,
                "amount_text": amount,
                "currency": "CNY",
                "direction": "out",
                "uncertain_fields": [],
                "evidence_text": f"价税合计 {amount}",
            }
        )
    (root / "receipt-06.png").write_bytes((root / "receipt-01.png").read_bytes())
    expected.append({**expected[0], "file_id": "receipt-06"})
    unclear = Image.new("RGB", (1040, 660), "white")
    ImageDraw.Draw(unclear).multiline_text(
        (55, 50),
        "SYNTHETIC DEMO / 合成测试票据\n发票号码: ???\n日期: ???\n销售方: ???\n金额: ???\n无法确认字段请留空。",
        fill="#444444",
        font=font,
        spacing=40,
    )
    unclear.save(root / "unclear.png")
    files = [
        FileRef(id=f"receipt-{i:02}", name=f"receipt-{i:02}.png", mime_type="image/png") for i in range(1, 7)
    ]
    rows = [
        {
            "transaction_id": f"payment-{i}",
            "date": receipt[2],
            "counterparty": receipt[3],
            "amount": "2850.00" if i == 5 else receipt[4],
            "direction": "out",
            "remark": "合成付款样例",
        }
        for i, receipt in enumerate(RECEIPTS, 1)
    ]
    rows.append(
        {
            "transaction_id": "payment-6",
            "date": "2026-10-15",
            "counterparty": "未附票据供应商",
            "amount": "129.00",
            "direction": "out",
            "remark": "缺票样例",
        }
    )
    with (root / "statement.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    transactions = [
        Transaction(
            id=row["transaction_id"],
            date=row["date"],
            counterparty=row["counterparty"],
            amount_minor=int(Decimal(row["amount"]) * 100),
            direction="out",
            source_file_id="statement",
            source_row=i + 2,
            remark=row["remark"],
        )
        for i, row in enumerate(rows)
    ]
    order = OrderInput(
        identity=RunIdentity(order_id="demo-order", run_id="demo-run", revision=1),
        company_name="松石设计工作室（合成样例）",
        period="2026-10",
        files=files,
        transactions=transactions,
    )
    write_json(root / "order.json", order.model_dump(mode="json"))
    write_json(root / "expected_extractions.json", expected)
    manifest = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.glob("*.png"))
    }
    write_json(root / "manifest.json", manifest)
    write_json(
        root / "expected_summary.json",
        {
            "matched_count": 4,
            "duplicate_count": 1,
            "amount_mismatch_count": 1,
            "difference_minor": 27000,
            "missing_invoice_count": 1,
        },
    )
    return manifest
