"""Customer-owned pre-order records; confirmation is one database transaction."""

from __future__ import annotations

import hashlib
import mimetypes
from copy import deepcopy
from datetime import timedelta
from pathlib import PurePosixPath, PureWindowsPath
from uuid import uuid4

from sqlalchemy import exists, select, update

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.types import utc_now
from app.intake.contracts import SERVICE
from app.intake.models import IntakeEvent, IntakeFile, IntakeJob, IntakeMessage, IntakeSession
from app.live import service as live
from app.live.models import OrderMessage
from app.models import AuditLog, Order, Studio, UploadedFile
from app.schemas.order import OrderCreate
from app.schemas.transaction import CSVImportCreate
from app.services import file_service, import_service, order_service
from app.services.csv_service import CSVService


def service_definition():
    return deepcopy(SERVICE)


async def owned(session, intake_id, principal):
    item = await session.get(IntakeSession, intake_id)
    if not item or (principal.role != "owner" and item.owner_user_id != principal.user_id):
        raise AppError("not_found", "接洽会话不存在。", 404)
    return item


async def files(session, intake_id):
    return list(
        (
            await session.scalars(
                select(IntakeFile)
                .where(IntakeFile.intake_id == intake_id)
                .order_by(IntakeFile.created_at, IntakeFile.id)
            )
        ).all()
    )


async def latest_precheck(session, intake_id):
    return await session.scalar(
        select(IntakeJob)
        .where(IntakeJob.intake_id == intake_id, IntakeJob.kind == "precheck")
        .order_by(IntakeJob.created_at.desc())
    )


async def event(session, intake_id, name, payload=None):
    session.add(IntakeEvent(intake_id=intake_id, event_type=name, payload=payload or {}))


async def mutable(session, item, revision):
    if item.order_id:
        raise AppError("intake_ordered", "已创建订单，请到订单中补充材料。", 409)
    active = await session.scalar(
        select(IntakeJob.id).where(
            IntakeJob.intake_id == item.id,
            IntakeJob.kind == "precheck",
            IntakeJob.status.in_(["queued", "running"]),
        )
    )
    if active:
        raise AppError("intake_busy", "材料正在预检，请完成后再修改。", 409)
    result = await session.execute(
        update(IntakeSession)
        .where(
            IntakeSession.id == item.id,
            IntakeSession.revision == revision,
            IntakeSession.order_id.is_(None),
            ~exists().where(
                IntakeJob.intake_id == item.id,
                IntakeJob.kind == "precheck",
                IntakeJob.status.in_(["queued", "running"]),
            ),
        )
        .values(revision=IntakeSession.revision + 1, status="collecting")
    )
    if result.rowcount != 1:
        raise AppError("stale_revision", "材料版本已变化，请刷新。", 409)
    await session.refresh(item)


async def create(session, principal):
    if principal.role != "customer":
        raise AppError("forbidden", "请使用客户身份创建咨询。", 403)
    item = IntakeSession(owner_user_id=principal.user_id)
    session.add(item)
    await session.flush()
    session.add(
        IntakeMessage(
            intake_id=item.id,
            role="assistant",
            content="欢迎咨询账清社。可以先发送问题或上传原始材料，材料 Agent 会列出待办并读取，再确认工作室和账期。确认前不会创建订单。",
        )
    )
    await event(session, item.id, "intake.created")
    await session.commit()
    return item


async def profile(session, item, data, principal):
    if data.studio_id:
        studio = await session.get(Studio, data.studio_id)
        if not studio or studio.owner_user_id != item.owner_user_id:
            raise AppError("invalid_studio", "工作室不属于本客户。", 422)
        if studio.name != data.studio_name.strip():
            raise AppError("invalid_studio", "已选工作室名称不一致。", 422)
    await mutable(session, item, data.expected_revision)
    item.studio_id = data.studio_id
    item.studio_name = data.studio_name.strip()
    item.period_start = data.period_start
    item.period_end = data.period_end
    item.profile_confirmed = data.profile_confirmed
    await event(session, item.id, "intake.profile.updated", {"revision": item.revision})
    await session.commit()


def prepare_file(name, data):
    ext = PurePosixPath(name.lower()).suffix
    if ext not in {".jpg", ".jpeg", ".png", ".csv"}:
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return "source_document", mime, "valid"
    category = (
        "bank_statement_csv"
        if ext == ".csv"
        else "invoice_image"
        if ext in {".jpg", ".jpeg", ".png"}
        else "unclassified"
    )
    mime, status = file_service.classify(
        name, category if category != "unclassified" else "supporting_material", data
    )
    return category, mime, status


async def upload(session, storage, item, uploads, revision):
    settings = get_settings()
    if not uploads or len(uploads) > settings.max_archive_files:
        raise AppError("upload_limit", "一次最多上传三十个文件。", 413)
    # Validate all archive paths and expansion limits before persisting any material metadata.
    prepared = []
    for upload in uploads:
        name = PureWindowsPath(upload.filename or "unnamed").name
        ext = PurePosixPath(name.lower()).suffix
        limit = (
            settings.max_archive_bytes
            if ext == ".zip"
            else settings.max_csv_bytes
            if ext == ".csv"
            else settings.max_image_bytes
        )
        data = await file_service.read_upload(upload, limit)
        if ext == ".zip":
            entries = file_service.inspect_archive(data, settings)
            prepared.append((name, data, entries))
        else:
            prepared.append((name, data, None))
    await mutable(session, item, revision)

    async def save(name, data, parent=None, path=None, archive=False):
        category, mime, status = (
            ("archive", "application/zip", "valid") if archive else prepare_file(name, data)
        )
        limit = settings.max_csv_bytes if category == "bank_statement_csv" else settings.max_image_bytes
        if not archive and len(data) > limit:
            raise AppError("file_too_large", "解压文件超过该类型大小限制。", 413)
        fid = str(uuid4())
        key = f"intakes/{item.id}/{fid}"
        storage.put(key, data)
        record = IntakeFile(
            id=fid,
            intake_id=item.id,
            original_filename=name,
            storage_key=key,
            category=category,
            mime_type=mime,
            validation_status=status,
            file_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            included=not archive,
            archive_file_id=parent,
            archive_entry_path=path,
        )
        session.add(record)
        await session.flush()
        return record

    saved = []
    for name, data, entries in prepared:
        root = await save(name, data, archive=entries is not None)
        saved.append(root)
        for info, content in entries or []:
            path = info.filename.replace("\\", "/")
            saved.append(await save(PurePosixPath(path).name, content, root.id, path))
    session.add(
        IntakeMessage(intake_id=item.id, role="user", content="已提交材料。", file_ids=[f.id for f in saved])
    )
    await event(session, item.id, "intake.files.updated", {"revision": item.revision})
    await session.commit()
    return saved


async def update_file(session, item, file_id, data):
    record = await session.get(IntakeFile, file_id)
    if not record or record.intake_id != item.id:
        raise AppError("not_found", "材料不存在。", 404)
    if record.category == "archive":
        raise AppError("archive_container", "原包仅保留追溯，请逐项选择包内材料。", 422)
    if data.category and not record.mime_type.startswith("image/"):
        raise AppError("invalid_category", "只能修正图片的票据或说明凭证类别。", 422)
    if record.replaced_by_file_id and data.included:
        raise AppError("replaced_file", "已被替换的材料不能再次纳入。", 409)
    old = await session.get(IntakeFile, data.replaces_file_id) if data.replaces_file_id else None
    if data.replaces_file_id and (
        not old
        or old.intake_id != item.id
        or old.id == record.id
        or old.category == "archive"
        or old.replaced_by_file_id
    ):
        raise AppError("invalid_replacement", "替换目标必须是本会话尚未替换的材料。", 422)
    await mutable(session, item, data.expected_revision)
    if data.category:
        record.category = data.category
        record.user_classified = True
    if data.included is not None:
        record.included = data.included
    if old:
        old.included = False
        old.replaced_by_file_id = record.id
    await event(session, item.id, "intake.files.updated", {"revision": item.revision})
    await session.commit()


def csv_parser():
    settings = get_settings()
    return CSVService(settings.csv_column_map, settings.csv_date_format, settings.csv_max_rows)


async def inspect_materials(session, item, storage, samples=None):
    materials = await files(session, item.id)
    active = [f for f in materials if f.included and f.category != "archive"]
    blockers = []
    warnings = []

    def issue(target, code, message, file_id=None):
        target.append(
            {
                "id": code + (":" + file_id if file_id else ""),
                "code": code,
                "message": message,
                "file_id": file_id,
            }
        )

    if not item.profile_confirmed or not item.studio_name or not item.period_start or not item.period_end:
        issue(blockers, "profile_required", "请确认工作室名称和账期。")
    invoices = [f for f in active if f.category == "invoice_image"]
    csvs = [f for f in active if f.category == "bank_statement_csv"]
    if len(invoices) > 20:
        issue(blockers, "invoice_limit", "有效票据不能超过二十张。")
    if len(csvs) != 1:
        issue(
            blockers, "statement_required", "还需要整理出一份可核验的收付款流水，或确认多份流水的处理范围。"
        )
    if not invoices:
        issue(warnings, "no_invoices", "未提交票据，仅核对已提交材料；缺票将列为异常。")
    hashes = {}
    csv_details = []
    for f in active:
        if f.validation_status != "valid":
            issue(blockers, "invalid_file", "文件无法读取或格式不支持，请排除或替换。", f.id)
        if f.category == "unclassified":
            issue(blockers, "category_required", "请选择材料类别或排除该文件。", f.id)
        if f.category == "source_document":
            issue(blockers, "document_pending", "这份原始文档还需要 Agent 读取并确认用途。", f.id)
        if f.sha256 in hashes:
            issue(warnings, "duplicate_file", "与另一份材料内容相同，正式处理将检查重复。", f.id)
        hashes[f.sha256] = f.id
        if f.category == "bank_statement_csv" and f.validation_status == "valid":
            try:
                parsed = csv_parser().parse(storage.read(f.storage_key))
                detail = {
                    "file_id": f.id,
                    "rows": parsed.total_rows,
                    "valid_rows": len(parsed.transactions),
                    "errors": [{"row_number": e.row_number, "reason": e.reason} for e in parsed.errors],
                }
                csv_details.append(detail)
                if parsed.errors or not parsed.transactions:
                    issue(blockers, "csv_rows_invalid", "CSV 存在错误行或没有有效交易，请替换。", f.id)
                if (
                    item.period_start
                    and item.period_end
                    and any(
                        not item.period_start <= r.transaction_date <= item.period_end
                        for r in parsed.transactions
                    )
                ):
                    issue(blockers, "csv_period_mismatch", "流水包含账期外记录，请调整账期或替换流水。", f.id)
            except AppError as error:
                issue(blockers, error.code, error.message, f.id)
    for fid, sample in (samples or {}).items():
        if not sample["readable"]:
            issue(warnings, "sample_unreadable", "抽查图片不够清晰，正式处理可能需要重新拍摄。", fid)
    return {
        "blockers": blockers,
        "warnings": warnings,
        "csv_details": csv_details,
        "invoice_count": len(invoices),
        "active_count": len(active),
        "sampled_file_ids": list(samples or {}),
        "skipped_file_ids": [f.id for f in active if f.mime_type.startswith("image/")],
        "note": "接洽阶段只收取票据图片并跳过预读；正式下单后再识别图片。流水文档由工具整理，后续仍可能发现未知字段、缺票和差额。",
    }


def customer_text(text, material):
    for f in material:
        text = text.replace(f.id, f.original_filename)
    for raw, label in {
        "inspect_intake_materials": "材料检查",
        "normalize_pdf_statement": "整理 PDF 流水",
        "normalize_statement": "整理流水",
        "prepare_pdf_receipts": "准备 PDF 票据页",
        "read_document": "读取文档",
        "read_image": "读取图片",
        "open_archive": "查看压缩包",
        "plan_materials": "安排材料待办",
        "save_precheck_result": "保存材料检查结论",
        "blockers": "启动待补项",
        "included=false": "仅保留原始包",
        "invoice_image": "票据",
        "supporting_material": "说明凭证",
        "archive": "压缩包",
    }.items():
        text = text.replace(raw, label)
    return text


async def snapshot(session, item, storage, *, owner=False):
    material = await files(session, item.id)
    job = await latest_precheck(session, item.id)
    fresh = bool(job and job.revision == item.revision and job.status == "succeeded")
    result = deepcopy(job.result) if fresh else None
    if result:
        result["narrative"]["summary"] = customer_text(result["narrative"]["summary"], material)
        result["narrative"]["questions"] = [
            customer_text(q, material) for q in result["narrative"]["questions"]
        ]
    todos = deepcopy((job.artifacts or {}).get("todos", [])) if job and job.revision == item.revision else []
    for task in todos:
        task["title"] = customer_text(task["title"], material)
        if task.get("detail") == "已取得真实工具结果。":
            task["detail"] = {
                "read_document": "已读取文件内容。",
                "normalize_statement": "已整理流水并保留原文件来源。",
                "inspect_archive": "已查看压缩包目录和内部文件。",
                "prepare_receipts": "已准备票据页图并保留页码。",
                "check_materials": "已检查资料，需要确认的事项会单独说明。",
            }.get(task["kind"], "已完成这项处理。")
        else:
            task["detail"] = customer_text(task.get("detail", ""), material)
    return {
        "id": item.id,
        "status": item.status,
        "revision": item.revision,
        "order_id": item.order_id,
        "studio_id": item.studio_id,
        "studio_name": item.studio_name,
        "period_start": str(item.period_start) if item.period_start else None,
        "period_end": str(item.period_end) if item.period_end else None,
        "profile_confirmed": item.profile_confirmed,
        "service": service_definition(),
        "files": [
            {
                k: getattr(f, k)
                for k in (
                    "id",
                    "original_filename",
                    "category",
                    "mime_type",
                    "file_size",
                    "sha256",
                    "validation_status",
                    "included",
                    "user_classified",
                    "archive_file_id",
                    "archive_entry_path",
                    "replaced_by_file_id",
                    "derived_from_file_id",
                )
            }
            for f in material
        ],
        "precheck": (
            {
                "id": job.id,
                "status": job.status,
                "revision": job.revision,
                "requests_used": job.requests_used,
                "request_limit": job.request_limit,
                "result": result,
                "todos": todos,
                "error": (
                    (job.error if owner else "预检未完成，请重试或联系老板。")
                    if job.status == "failed"
                    else None
                ),
            }
            if job
            else None
        ),
        "confirmation": (
            {
                "precheck_id": job.id,
                "revision": item.revision,
                "service_version": SERVICE["version"],
                "price_cents": SERVICE["price_cents"],
                "warnings": result["warnings"],
                "deliverables": SERVICE["deliverables"],
                "is_simulated": True,
            }
            if result and not result["blockers"] and not item.order_id
            else None
        ),
    }


async def start_precheck(session, item, revision):
    if item.order_id:
        raise AppError("intake_ordered", "请在订单中处理后续材料。", 409)
    if revision != item.revision:
        raise AppError("stale_revision", "材料版本已变化。", 409)
    guard = await session.execute(
        update(IntakeSession)
        .where(
            IntakeSession.id == item.id, IntakeSession.revision == revision, IntakeSession.order_id.is_(None)
        )
        .values(revision=IntakeSession.revision)
    )
    if guard.rowcount != 1:
        raise AppError("stale_revision", "材料版本已变化，请刷新。", 409)
    existing = await session.scalar(
        select(IntakeJob).where(
            IntakeJob.intake_id == item.id, IntakeJob.operation_key == f"precheck:{revision}"
        )
    )
    if existing:
        if existing.status == "failed":
            existing.status = "queued"
            existing.error = None
            existing.artifacts = {
                k: v for k, v in existing.artifacts.items() if k not in {"inspection_progress", "stalled"}
            }
            item.status = "checking"
        await session.commit()
        return existing
    claimed = await session.execute(
        update(IntakeSession)
        .where(
            IntakeSession.id == item.id, IntakeSession.revision == revision, IntakeSession.order_id.is_(None)
        )
        .values(status="checking")
    )
    if claimed.rowcount != 1:
        raise AppError("stale_revision", "材料版本已变化，请刷新。", 409)
    job = IntakeJob(
        intake_id=item.id,
        kind="precheck",
        revision=revision,
        operation_key=f"precheck:{revision}",
        request_limit=None,
    )
    session.add(job)
    item.status = "checking"
    await event(session, item.id, "precheck.queued", {"revision": revision})
    await session.commit()
    return job


async def post_message(session, item, data):
    if item.order_id:
        raise AppError("intake_ordered", "请继续订单会话。", 409)
    old = await session.scalar(
        select(IntakeMessage).where(
            IntakeMessage.intake_id == item.id, IntakeMessage.client_message_id == data.client_message_id
        )
    )
    if old:
        return old
    permitted = {f.id for f in await files(session, item.id)}
    if not set(data.file_ids) <= permitted:
        raise AppError("invalid_message_file", "消息附件不属于本会话。", 422)
    message = IntakeMessage(
        intake_id=item.id,
        role="user",
        content=data.content,
        file_ids=data.file_ids,
        client_message_id=data.client_message_id,
    )
    session.add(message)
    await session.flush()
    if data.intent == "question":
        message.status = "queued"
        job = IntakeJob(
            intake_id=item.id,
            kind="chat",
            operation_key="message:" + message.id,
            revision=item.revision,
            request_limit=6,
            source_message_id=message.id,
        )
        session.add(job)
        await session.flush()
        message.job_id = job.id
    await event(session, item.id, "message.created")
    await session.commit()
    return message


async def confirm(session, item, data, principal, storage):
    if principal.role != "customer" or principal.user_id != item.owner_user_id:
        raise AppError("forbidden", "只有客户本人可以确认下单。", 403)
    if item.order_id:
        order = await session.get(Order, item.order_id)
        run = await live.current_run(session, order.id)
        return {
            "order_id": order.id,
            "order_no": order.order_no,
            "run_id": run.id,
            "price_cents": order.price_cents,
        }
    job = await session.get(IntakeJob, data.precheck_id)
    if (
        not job
        or job.intake_id != item.id
        or job.kind != "precheck"
        or job.status != "succeeded"
        or job.revision != item.revision
        or data.expected_revision != item.revision
    ):
        raise AppError("stale_precheck", "请基于最新材料完成预检后再确认。", 409)
    if data.service_version != SERVICE["version"]:
        raise AppError("stale_service", "服务版本已变化，请刷新。", 409)
    checks = await inspect_materials(session, item, storage, job.result.get("samples"))
    if checks["blockers"]:
        raise AppError("materials_not_ready", "材料未满足启动条件。", 409)
    if not {w["id"] for w in checks["warnings"]} <= set(data.acknowledged_warning_ids):
        raise AppError("warnings_unacknowledged", "请确认服务卡中的每项待确认事项。", 422)
    claim = await session.execute(
        update(IntakeSession)
        .where(
            IntakeSession.id == item.id,
            IntakeSession.revision == data.expected_revision,
            IntakeSession.order_id.is_(None),
            IntakeSession.status.in_(["ready", "ready_with_warnings"]),
        )
        .values(status="confirming")
    )
    if claim.rowcount != 1:
        await session.rollback()
        await session.refresh(item)
        if item.order_id:
            return await confirm(session, item, data, principal, storage)
        raise AppError("confirmation_conflict", "当前确认卡已变化，请刷新。", 409)
    if item.studio_id:
        studio = await session.get(Studio, item.studio_id)
        if not studio or studio.owner_user_id != principal.user_id:
            raise AppError("invalid_studio", "工作室归属已变化。", 409)
    else:
        studio = Studio(name=item.studio_name, owner_user_id=principal.user_id, business_type="small_studio")
        session.add(studio)
        await session.flush()
    order = await order_service.create_order(
        session,
        OrderCreate(
            studio_id=studio.id,
            period_start=item.period_start,
            period_end=item.period_end,
            service_scope=item.service_code,
        ),
        principal,
        commit=False,
    )
    order.intake_id = item.id
    order.service_snapshot = service_definition()
    order.price_cents = SERVICE["price_cents"]
    material = await files(session, item.id)
    mapping = {f.id: str(uuid4()) for f in material}
    for f in material:
        mapped = UploadedFile(
            id=mapping[f.id],
            order_id=order.id,
            original_filename=f.original_filename,
            storage_key=f.storage_key,
            file_category=f.category if f.category != "unclassified" else "supporting_material",
            mime_type=f.mime_type,
            file_size=f.file_size,
            sha256=f.sha256,
            validation_status=f.validation_status,
            upload_source="archive" if f.archive_file_id else "direct",
            archive_file_id=mapping.get(f.archive_file_id),
            archive_entry_path=f.archive_entry_path,
            is_active=f.included and f.category != "archive",
            replaced_by_file_id=mapping.get(f.replaced_by_file_id),
        )
        session.add(mapped)
        f.order_file_id = mapped.id
    await session.flush()
    statement = next(f for f in material if f.included and f.category == "bank_statement_csv")
    imported = await import_service.import_csv(
        session,
        storage,
        order.id,
        CSVImportCreate(file_id=mapping[statement.id]),
        principal,
        get_settings(),
        commit=False,
    )
    if imported.failed_rows:
        raise AppError("csv_changed", "流水校验未通过，订单没有创建。", 409)
    messages = (
        await session.scalars(
            select(IntakeMessage).where(IntakeMessage.intake_id == item.id).order_by(IntakeMessage.created_at)
        )
    ).all()
    for msg in messages:
        session.add(
            OrderMessage(
                order_id=order.id,
                client_message_id="intake:" + msg.id,
                role=msg.role,
                content=msg.content,
                status=msg.status,
                file_ids=[mapping[fid] for fid in msg.file_ids if fid in mapping],
                input_revision=order.input_revision,
                created_at=msg.created_at,
            )
        )
    session.add(
        OrderMessage(
            order_id=order.id,
            role="assistant",
            content="服务已确认。总管将安排正式识别与核对，已知待确认事项会继续保留。",
            input_revision=order.input_revision,
        )
    )
    run = await live.start_run(
        session, order.id, principal, "intake-confirm:" + item.id, order.input_revision, commit=False
    )
    item.order_id = order.id
    item.status = "ordered"
    item.confirmation_key = data.idempotency_key
    session.add(
        AuditLog(
            order_id=order.id,
            actor_type="customer",
            actor_id=principal.user_id,
            action="intake.confirmed",
            entity_type="intake",
            entity_id=item.id,
            details={
                "precheck_id": job.id,
                "revision": item.revision,
                "warnings": data.acknowledged_warning_ids,
            },
        )
    )
    await event(session, item.id, "intake.ordered", {"order_id": order.id, "run_id": run.id})
    await session.commit()
    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "run_id": run.id,
        "price_cents": order.price_cents,
    }


async def queued(session, kind):
    now = utc_now()
    return await session.scalar(
        select(IntakeJob)
        .where(
            IntakeJob.kind == kind,
            (IntakeJob.status == "queued")
            | ((IntakeJob.status == "running") & (IntakeJob.lease_expires_at < now)),
        )
        .order_by(IntakeJob.created_at)
        .limit(1)
    )


async def claim(session, job_id, token):
    now = utc_now()
    result = await session.execute(
        update(IntakeJob)
        .where(
            IntakeJob.id == job_id,
            (IntakeJob.status == "queued")
            | ((IntakeJob.status == "running") & (IntakeJob.lease_expires_at < now)),
        )
        .values(
            status="running",
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=60),
            heartbeat_at=now,
            error=None,
        )
    )
    await session.commit()
    return result.rowcount == 1
