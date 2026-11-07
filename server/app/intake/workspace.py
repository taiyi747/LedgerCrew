"""Capability-scoped document tools: only this intake's file IDs, no shell or host paths."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy import select

from app.agents.errors import AgentError
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.intake import service
from app.intake.models import IntakeFile
from app.services.file_service import inspect_archive

FIELDS = ("transaction_date", "counterparty", "direction", "amount", "description", "external_id")
KINDS = {"inspect_archive", "read_document", "normalize_statement", "prepare_receipts", "check_materials"}


def decode_text(content):
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文本编码无法识别，请提供可读的原始文件。")


def safe_package(content):
    """Bound decompression before handing an Office package to a document reader."""
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        entries = package.infolist()
        if len(entries) > 2000 or sum(p.file_size for p in entries) > 50 * 1024 * 1024:
            raise ValueError("文档展开后超过工作区大小限制。")
        if any(
            p.file_size > 25 * 1024 * 1024
            or (p.file_size > 1000 and p.file_size > max(p.compress_size, 1) * 300)
            for p in entries
        ):
            raise ValueError("文档内部压缩内容超过工作区限制。")


def cell_text(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return "" if value is None else str(value).strip()


def document_data(name, content):
    """Read bounded source data, retaining row numbers and raw text for tool verification."""
    suffix = PurePosixPath(name.lower()).suffix
    if suffix in {".csv", ".tsv"}:
        text = decode_text(content)
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        if len(rows) > get_settings().csv_max_rows + 20:
            raise ValueError("表格超过本次服务可处理的行数。")
        return {
            "type": "table",
            "sheets": [{"name": "CSV", "rows": [[cell_text(c) for c in row[:40]] for row in rows]}],
        }
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        safe_package(content)
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            if len(book.worksheets) > 10:
                raise ValueError("工作表数量超过本次工作区限制。")
            sheets = []
            for sheet in book.worksheets:
                if (sheet.max_row or 0) > get_settings().csv_max_rows + 20 or (sheet.max_column or 0) > 40:
                    raise ValueError("工作表行数或列数超过本次工作区限制。")
                sheets.append(
                    {
                        "name": sheet.title,
                        "rows": [[cell_text(c) for c in row] for row in sheet.iter_rows(values_only=True)],
                    }
                )
            return {"type": "table", "sheets": sheets}
        finally:
            book.close()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise ValueError("PDF 已加密，需要客户提供可读取的副本。")
        if len(reader.pages) > 20:
            raise ValueError("PDF 超过本次可读取的二十页。")
        lines = []
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            lines.extend(
                {"line": len(lines) + i + 1, "page": page_number, "text": line[:2000]}
                for i, line in enumerate(text.splitlines())
                if line.strip()
            )
        if sum(len(line["text"]) for line in lines) > 100_000:
            raise ValueError("PDF 文本超过工作区读取限制。")
        # Re-number after blank-line removal so evidence IDs are stable and unique.
        for i, line in enumerate(lines, 1):
            line["line"] = i
        return {"type": "pdf", "pages": len(reader.pages), "lines": lines}
    if suffix in {".txt", ".md", ".json"}:
        text = decode_text(content)
        if len(text) > 100_000:
            raise ValueError("文档文本超过工作区读取限制。")
        return {"type": "text", "text": text}
    if suffix == ".docx":
        from xml.etree import ElementTree

        safe_package(content)
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            body = package.read("word/document.xml")
        root = ElementTree.fromstring(body)
        text = "\n".join(
            p.text or "" for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        )
        return {"type": "text", "text": text[:100_000]}
    raise ValueError("当前读取工具不能解析这份材料；请向客户说明具体文件和需要确认的内容。")


def money_text(raw):
    raw = re.sub(r"[人民币元¥￥,，\s]", "", str(raw))
    try:
        amount = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError("金额无法确定：" + raw) from error
    if not amount.is_finite() or abs(amount) > Decimal("92233720368547758.07"):
        raise ValueError("金额超出可处理范围。")
    if amount.quantize(Decimal(".01")) != amount:
        raise ValueError("金额包含无效数值或超过两位小数。")
    return amount


def date_text(raw):
    raw = str(raw).strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y年%m月%d日",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("日期无法确定：" + raw)


def canonical_row(raw, source_id, row_number):
    amount = money_text(raw["amount"])
    direction = str(raw["direction"]).strip().upper()
    direction = {
        "收入": "IN",
        "收": "IN",
        "入": "IN",
        "贷": "IN",
        "支出": "OUT",
        "支": "OUT",
        "出": "OUT",
        "借": "OUT",
        "付款": "OUT",
        "收款": "IN",
        "转出": "OUT",
        "转入": "IN",
        "借方": "OUT",
        "贷方": "IN",
    }.get(direction, direction)
    if direction not in {"IN", "OUT"}:
        raise ValueError("收支方向无法确定，不能根据正数金额猜测。")
    if direction == "IN" and amount < 0:
        raise ValueError("收入方向与负数金额矛盾，需要核实，不能直接取绝对值。")
    if not str(raw["counterparty"]).strip():
        raise ValueError("缺少交易对方，需要客户确认。")
    return [
        date_text(raw["transaction_date"]),
        str(raw["counterparty"]).strip(),
        direction,
        format(abs(amount), ".2f"),
        raw.get("description", ""),
        raw.get("external_id") or f"{source_id[:8]}-row-{row_number}",
    ]


class MaterialWorkspace:
    def __init__(self, sessions, store, identity, intake_id, storage):
        self.sessions, self.store, self.identity = sessions, store, identity
        self.intake_id, self.storage = intake_id, storage
        self.lock = asyncio.Lock()

    async def source(self, file_id):
        async with self.sessions() as session:
            await self.store.job(session)
            record = await session.get(IntakeFile, file_id)
            if not record or record.intake_id != self.intake_id:
                raise ValueError("工作区只能读取当前咨询的材料 ID。")
            return record

    async def save(self, key, payload):
        return await self.store.save_artifact(self.identity, key, payload, key)

    async def plan(self, tasks):
        async with self.lock:
            async with self.sessions() as session:
                await self.store.job(session)
                allowed = {f.id for f in await service.files(session, self.intake_id)}
            old = {t["id"]: t for t in await self.store.load_artifact(self.identity, "todos") or []}
            result = list(old.values())
            task_ids = set()
            if len(tasks) > 100:
                raise ValueError("待办数量超过本次材料工作区限制。")
            for task in tasks:
                kind, fid = task.get("kind"), task.get("file_id", "")
                if kind not in KINDS or (kind != "check_materials" and fid not in allowed):
                    raise ValueError("待办类型或材料不属于本咨询。")
                key = kind + ":" + fid
                if key in task_ids:
                    raise ValueError("同一份材料的同类待办不能重复。")
                task_ids.add(key)
                title = str(task.get("title", ""))[:120]
                if not title:
                    raise ValueError("请为待办填写客户能理解的任务名称。")
                if key not in old:
                    result.append(
                        {
                            "id": key,
                            "file_id": fid,
                            "kind": kind,
                            "title": title,
                            "status": "pending",
                            "detail": "",
                        }
                    )
            await self.save("todos", result)
            await self.notify()
            return json.dumps(result, ensure_ascii=False)

    async def notify(self):
        async with self.sessions() as session:
            await self.store.job(session)
            await service.event(session, self.intake_id, "workspace.updated")
            await session.commit()

    async def task_status(self, kind, file_id, status, detail=""):
        todos = await self.store.load_artifact(self.identity, "todos") or []
        for task in todos:
            if task["kind"] == kind and (task["file_id"] == file_id or kind == "check_materials"):
                task["status"], task["detail"] = status, detail[:300]
        await self.save("todos", todos)
        await self.notify()

    async def run(self, kind, file_id, operation):
        async with self.lock:
            todos = await self.store.load_artifact(self.identity, "todos")
            if not todos or not any(
                t["kind"] == kind and (t["file_id"] == file_id or kind == "check_materials") for t in todos
            ):
                return json.dumps(
                    {"error": "请先调用 plan_materials，为这份材料安排对应待办。"}, ensure_ascii=False
                )
            await self.task_status(kind, file_id, "running")
            try:
                result = await operation()
                receipt_key = "receipt:" + kind + ":" + file_id
                prior = await self.store.load_artifact(self.identity, receipt_key)
                repeat_key = "repeat:" + kind + ":" + file_id
                previous = await self.store.load_artifact(self.identity, repeat_key) or {}
                repeats = previous.get("count", 0) + 1 if prior == result else 0
                await self.save(repeat_key, {"count": repeats})
                if repeats >= 3:
                    raise AgentError("材料工具连续重复同一结果，没有产生新成果。")
                await self.save(receipt_key, result)
                await self.task_status(kind, file_id, "completed", "已取得真实工具结果。")
                return json.dumps(result, ensure_ascii=False)
            except (ValueError, AppError, OSError, zipfile.BadZipFile) as error:
                message = error.message if isinstance(error, AppError) else str(error)
                await self.task_status(kind, file_id, "blocked", message)
                return json.dumps({"error": message, "file_id": file_id}, ensure_ascii=False)

    async def list_files(self):
        async with self.sessions() as session:
            await self.store.job(session)
            return [
                {
                    "id": f.id,
                    "name": f.original_filename,
                    "type": f.mime_type,
                    "included": f.included,
                    "category": f.category,
                    "source_file_id": f.derived_from_file_id,
                }
                for f in await service.files(session, self.intake_id)
            ]

    async def open_archive(self, file_id):
        source = await self.source(file_id)
        entries = inspect_archive(self.storage.read(source.storage_key), get_settings())
        children = [f for f in await self.list_files() if f["id"] != file_id]
        return {
            "archive": source.original_filename,
            "entries": [{"path": info.filename, "bytes": len(content)} for info, content in entries],
            "workspace_files": children,
        }

    async def read(self, file_id):
        source = await self.source(file_id)
        if source.mime_type.startswith("image/"):
            raise ValueError("图片请调用 read_image 工具。")
        try:
            result = document_data(source.original_filename, self.storage.read(source.storage_key))
        except ValueError:
            raise
        except Exception as error:
            raise ValueError("文件内容无法由当前读取器解析：" + type(error).__name__) from error
        await self.save("document:" + file_id, result)
        return result

    async def derived(self, source, name, content, category, mime, recipe):
        digest = hashlib.sha256(json.dumps(recipe, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        key = self.intake_id + ":" + digest
        async with self.sessions() as session:
            await self.store.job(session)
            existing = await session.scalar(select(IntakeFile).where(IntakeFile.derivation_key == key))
            if existing:
                if category == "bank_statement_csv":
                    siblings = (
                        await session.scalars(
                            select(IntakeFile).where(
                                IntakeFile.derived_from_file_id == source.id,
                                IntakeFile.category == "bank_statement_csv",
                            )
                        )
                    ).all()
                    for sibling in siblings:
                        sibling.included = sibling.id == existing.id
                    await session.commit()
                return existing.id
            current = await session.get(IntakeFile, source.id)
            current.included = False
            current.category = "supporting_material"
            if category == "bank_statement_csv":
                siblings = (
                    await session.scalars(
                        select(IntakeFile).where(
                            IntakeFile.derived_from_file_id == source.id,
                            IntakeFile.category == "bank_statement_csv",
                        )
                    )
                ).all()
                for sibling in siblings:
                    sibling.included = False
            fid = str(uuid4())
            storage_key = f"intakes/{self.intake_id}/{fid}"
            self.storage.put(storage_key, content)
            session.add(
                IntakeFile(
                    id=fid,
                    intake_id=self.intake_id,
                    original_filename=name,
                    storage_key=storage_key,
                    category=category,
                    mime_type=mime,
                    file_size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                    validation_status="valid",
                    included=True,
                    derived_from_file_id=source.id,
                    derivation_key=key,
                )
            )
            await service.event(
                session,
                self.intake_id,
                "workspace.material.created",
                {"file_id": fid, "source_file_id": source.id},
            )
            await session.commit()
            return fid

    async def normalize_table(self, file_id, mapping, sheet_name="", header_row=1):
        source = await self.source(file_id)
        document = await self.store.load_artifact(self.identity, "document:" + file_id)
        if not document or document.get("type") != "table":
            raise ValueError("先通过 read_document 读取源表格，再依据真实表头映射字段。")
        sheet = next((s for s in document["sheets"] if not sheet_name or s["name"] == sheet_name), None)
        if not sheet or not 1 <= header_row <= len(sheet["rows"]):
            raise ValueError("工作表或表头行无效。")
        headers = sheet["rows"][header_row - 1]
        if any(headers.count(column) != 1 for column in mapping.values()):
            raise ValueError("存在重复表头，请先向客户核实列的含义。")
        if any(value not in headers for value in mapping.values()):
            raise ValueError("映射列必须来自实际读取的表头。")
        if not {"transaction_date", "counterparty"} <= mapping.keys():
            raise ValueError("需要确认日期和交易对方所在列。")
        result = []
        for number, values in enumerate(sheet["rows"][header_row:], header_row + 1):
            if not any(values):
                continue
            raw = {
                field: values[headers.index(column)] if headers.index(column) < len(values) else ""
                for field, column in mapping.items()
            }
            if "income_amount" in raw or "expense_amount" in raw:
                income = money_text(raw.get("income_amount") or "0")
                expense = money_text(raw.get("expense_amount") or "0")
                if (income > 0) == (expense > 0):
                    raise ValueError(f"第 {number} 行收入/支出不能同时非零或同时为空。")
                raw["amount"], raw["direction"] = (str(income), "IN") if income > 0 else (str(expense), "OUT")
            if not {"amount", "direction"} <= raw.keys():
                raise ValueError("需要收支方向与金额列，或分别提供收入列、支出列。")
            result.append(canonical_row(raw, source.id, number))
        return await self.save_statement(
            source,
            result,
            {"source": source.id, "sheet": sheet["name"], "header_row": header_row, "mapping": mapping},
        )

    async def normalize_pdf_rows(self, file_id, rows):
        source = await self.source(file_id)
        document = await self.store.load_artifact(self.identity, "document:" + file_id)
        if not document or document.get("type") != "pdf":
            raise ValueError("先读取 PDF 文本，逐行引用真实文本行号。")
        lines = {str(row["line"]): row["text"] for row in document["lines"]}
        result = []
        for row in rows:
            number = str(row.get("source_line", ""))
            if number not in lines:
                raise ValueError("PDF 行号不存在。")
            for field in ("transaction_date", "counterparty", "amount", "direction"):
                if not row.get(field) or row[field] not in lines[number]:
                    raise ValueError("PDF 日期、对方、金额和方向必须逐字引用同一源文本行，不能补造。")
            result.append(canonical_row(row, source.id, int(number)))
        return await self.save_statement(source, result, {"source": source.id, "rows": rows})

    async def save_statement(self, source, rows, recipe):
        if not rows or len(rows) > get_settings().csv_max_rows:
            raise ValueError("没有可核验的流水，或流水超过本次服务行数限制。")
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        writer.writerows(rows)
        content = stream.getvalue().encode("utf-8-sig")
        parsed = service.csv_parser().parse(content)
        if parsed.errors or len(parsed.transactions) != len(rows):
            raise ValueError("规范化流水未通过确定性校验。")
        fid = await self.derived(
            source,
            PurePosixPath(source.original_filename).stem + "_已整理.csv",
            content,
            "bank_statement_csv",
            "text/csv",
            recipe,
        )
        await self.save(
            "normalization:" + source.id,
            {"file_id": fid, "source_file_id": source.id, "rows": len(rows), "recipe": recipe},
        )
        return {
            "file_id": fid,
            "source_file_id": source.id,
            "rows": len(rows),
            "message": "原始金额由代码转换，已保存带来源的内部流水。",
        }

    async def render_pdf(self, file_id, pages):
        import pypdfium2 as pdfium

        source = await self.source(file_id)
        if not pages or len(set(pages)) != len(pages) or len(pages) > 20:
            raise ValueError("请提供不重复的 PDF 页码。")
        try:
            doc = pdfium.PdfDocument(self.storage.read(source.storage_key))
        except pdfium.PdfiumError as error:
            raise ValueError("PDF 内容无法渲染，请核实原件。") from error
        outputs = []
        try:
            if any(page < 1 or page > len(doc) for page in pages):
                raise ValueError("PDF 页码不存在。")
            for number in pages:
                page = doc[number - 1]
                try:
                    # Bound pixel count even when the page dimensions are unusually large.
                    width, height = page.get_size()
                    scale = min(1.6, 1600 / max(width, height))
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        out = io.BytesIO()
                        image.save(out, format="PNG")
                        image.close()
                    finally:
                        bitmap.close()
                    fid = await self.derived(
                        source,
                        f"{PurePosixPath(source.original_filename).stem}_第{number}页.png",
                        out.getvalue(),
                        "invoice_image",
                        "image/png",
                        {"source": source.id, "page": number},
                    )
                    outputs.append({"file_id": fid, "source_file_id": source.id, "page": number})
                finally:
                    page.close()
        finally:
            doc.close()
        return {"pages": outputs}
