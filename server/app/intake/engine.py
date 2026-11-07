"""Bounded Flash reception agents. No order or reconciliation tools are exposed."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from sqlalchemy import select, update

from app.agents.config import Settings
from app.agents.contracts import RunIdentity
from app.agents.errors import AgentError
from app.agents.runner import MiMoRunner, RequestBudget
from app.db.types import utc_now
from app.intake import service
from app.intake.contracts import ImageSample, IntakeAnswer, PrecheckNarrative
from app.intake.models import IntakeFile, IntakeJob, IntakeMessage, IntakeSession
from app.live import service as live
from app.live.models import OrderMessage
from app.storage.local import get_storage


class IntakeBudgetStore:
    def __init__(self, sessions, job_id, token):
        self.sessions, self.job_id, self.token = sessions, job_id, token

    async def job(self, session):
        job = await session.get(IntakeJob, self.job_id)
        if (
            not job
            or job.status != "running"
            or job.lease_token != self.token
            or not job.lease_expires_at
            or job.lease_expires_at <= utc_now()
        ):
            raise AgentError("接洽任务租约已失效。")
        item = await session.get(IntakeSession, job.intake_id)
        if job.kind == "precheck" and item.revision != job.revision:
            raise AgentError("预检材料版本已变化。")
        return job

    async def load_artifact(self, identity, kind):
        async with self.sessions() as s:
            job = await self.job(s)
            if kind == "usage":
                return {"requests": job.requests_used, "limit": job.request_limit}
            return job.artifacts.get(kind)

    async def save_artifact(self, identity, kind, payload, idempotency_key):
        async with self.sessions() as s:
            job = await self.job(s)
            if kind == "usage":
                if payload["requests"] != job.requests_used + 1 or (
                    job.request_limit is not None and payload["requests"] > job.request_limit
                ):
                    raise AgentError("接洽请求预算冲突或耗尽。")
                job.requests_used = payload["requests"]
            else:
                key = idempotency_key if kind in {"wire_request", "model_usage"} else kind
                values = dict(job.artifacts)
                values[key] = payload
                job.artifacts = values
            await s.commit()
            return idempotency_key


async def save_answer(session, item, job, content, status="completed", refs=None):
    old = await session.scalar(
        select(IntakeMessage).where(
            IntakeMessage.intake_id == item.id, IntakeMessage.client_message_id == "answer:" + job.id
        )
    )
    if old and (old.status == "completed" or status != "completed"):
        return
    if old:
        message = old
        message.content, message.status, message.file_ids = content, status, refs or []
    else:
        message = IntakeMessage(
            intake_id=item.id,
            job_id=job.id,
            client_message_id="answer:" + job.id,
            role="assistant",
            content=content,
            status=status,
            file_ids=refs or [],
        )
        session.add(message)
    await session.flush()
    if job.source_message_id:
        (await session.get(IntakeMessage, job.source_message_id)).status = status
    if item.order_id:
        material = await service.files(session, item.id)
        mapping = {f.id: f.order_file_id for f in material}
        mirrored = await session.scalar(
            select(OrderMessage).where(
                OrderMessage.order_id == item.order_id,
                OrderMessage.client_message_id == "intake:" + message.id,
            )
        )
        order_refs = [mapping[f] for f in refs or [] if mapping.get(f)]
        if mirrored:
            mirrored.content, mirrored.status, mirrored.file_ids = content, status, order_refs
        else:
            session.add(
                OrderMessage(
                    order_id=item.order_id,
                    client_message_id="intake:" + message.id,
                    role="assistant",
                    content=content,
                    status=status,
                    file_ids=order_refs,
                )
            )
        await live.event(session, item.order_id, "message.assistant.completed")


async def execute_job(sessions, job_id, token, *, runner=None, storage=None, raise_errors=False):
    store = IntakeBudgetStore(sessions, job_id, token)
    runner = runner or MiMoRunner(Settings.from_env())
    storage = storage or get_storage()
    async with sessions() as session:
        job = await store.job(session)
        item = await session.get(IntakeSession, job.intake_id)
        identity = RunIdentity(order_id="intake_" + item.id, run_id=job.id, revision=job.revision)
        kind = job.kind
        intake_id = item.id
    budget = RequestBudget(store, identity, job.request_limit)

    async def heartbeat():
        while True:
            await asyncio.sleep(5)
            async with sessions() as s:
                changed = await s.execute(
                    update(IntakeJob)
                    .where(
                        IntakeJob.id == job_id, IntakeJob.status == "running", IntakeJob.lease_token == token
                    )
                    .values(heartbeat_at=utc_now(), lease_expires_at=utc_now() + timedelta(seconds=60))
                )
                await s.commit()
                if changed.rowcount == 0:
                    return

    pulse = asyncio.create_task(heartbeat())
    try:

        async def context():
            async with sessions() as s:
                await store.job(s)
                item = await s.get(IntakeSession, intake_id)
                return await service.snapshot(s, item, storage)

        if kind == "chat":
            async with sessions() as s:
                job = await store.job(s)
                source = await s.get(IntakeMessage, job.source_message_id)
                question = source.content
            state = await context()
            allowed = {f["id"] for f in state["files"]}
            cached = await store.load_artifact(identity, "answer")
            if cached:
                answer = IntakeAnswer.model_validate(cached)
            else:
                answer = await runner.generate(
                    "customer_service",
                    "你是下单前客服。只解释本服务和本会话材料；不能创建订单、改价格、声称已对账或已完整识别。"
                    "询问缺失的工作室/账期，提醒检查材料后由客户点确认创建订单。"
                    "evidence_refs 只能使用 allowed_evidence_refs 中的 id，没有引用用空数组。\n"
                    + json.dumps(
                        {"question": question, "context": state, "allowed_evidence_refs": sorted(allowed)},
                        ensure_ascii=False,
                    ),
                    IntakeAnswer,
                    budget,
                )
                if not set(answer.evidence_refs) <= allowed:
                    raise AgentError("接洽答复引用了其他材料。")
                await store.save_artifact(identity, "answer", answer.model_dump(mode="json"), "answer")
            async with sessions() as s:
                job = await store.job(s)
                item = await s.get(IntakeSession, intake_id)
                await save_answer(s, item, job, answer.answer, refs=answer.evidence_refs)
                job.status = "succeeded"
                job.result = answer.model_dump(mode="json")
                job.lease_token = job.lease_expires_at = None
                await service.event(s, intake_id, "message.completed")
                await s.commit()
            return

        async def read_material_manifest() -> str:
            """读取本会话真实材料清单、CSV 校验、启动阻塞及警告。"""
            async with sessions() as s:
                await store.job(s)
                item = await s.get(IntakeSession, intake_id)
                checks = await service.inspect_materials(s, item, storage)
                manifest = [
                    {
                        "id": f.id,
                        "name": f.original_filename,
                        "category": f.category,
                        "mime_type": f.mime_type,
                        "included": f.included,
                    }
                    for f in await service.files(s, intake_id)
                ]
            result = {"checks": checks, "files": manifest}
            await store.save_artifact(identity, "manifest_read", result, "manifest_read")
            return json.dumps(result, ensure_ascii=False)

        async def inspect_sample_images() -> str:
            """按清单顺序抽查最多三张不同哈希图片，只判断类型与清晰度，不提取财务字段。"""
            async with sessions() as s:
                await store.job(s)
                material = await service.files(s, intake_id)
                chosen = []
                seen = set()
                for f in material:
                    if (
                        f.included
                        and f.validation_status == "valid"
                        and f.mime_type.startswith("image/")
                        and f.sha256 not in seen
                    ):
                        seen.add(f.sha256)
                        chosen.append(f)
                    if len(chosen) == 3:
                        break
            samples = {}
            for f in chosen:
                saved = await store.load_artifact(identity, "sample:" + f.id)
                if saved:
                    sample = ImageSample.model_validate(saved)
                else:
                    sample = await runner.generate(
                        "customer_service",
                        "仅做材料抽查，不读取或返回发票金额、号码等财务字段。判断图片属于票据 invoice_image、"
                        "说明/支付凭证 supporting_material 或无法确定 unclassified。判断是否清晰可读，不能保证真实性。"
                        "file_id 必须为 " + f.id,
                        ImageSample,
                        budget,
                        image=(storage.read(f.storage_key), f.mime_type),
                    )
                    if sample.file_id != f.id:
                        raise AgentError("抽查图片标识不符。")
                    await store.save_artifact(
                        identity, "sample:" + f.id, sample.model_dump(mode="json"), "sample:" + f.id
                    )
                samples[f.id] = sample.model_dump(mode="json")
            await store.save_artifact(identity, "samples", samples, "samples")
            return json.dumps(samples, ensure_ascii=False)

        async def inspect_intake_materials() -> str:
            """读取本会话清单与 CSV 检查，并抽查最多三张不同图片，不进行正式识别或对账。"""
            manifest = json.loads(await read_material_manifest())
            manifest["samples"] = json.loads(await inspect_sample_images())
            marker = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
            prior = await store.load_artifact(identity, "inspection_progress") or {}
            repeats = prior.get("repeats", 0) + 1 if prior.get("marker") == marker else 0
            await store.save_artifact(
                identity, "inspection_progress", {"marker": marker, "repeats": repeats}, "inspection_progress"
            )
            if repeats >= 3:
                await store.save_artifact(
                    identity, "stalled", {"reason": "连续重复检查没有产生新成果。"}, "stalled"
                )
                raise AgentError("预检连续重复同一检查且未保存成果，请人工检查后重试。")
            return json.dumps(manifest, ensure_ascii=False)

        async def save_precheck_result(summary: str, questions: list[str], evidence_refs: list[str]) -> str:
            """保存有工具依据的预检说明；启动条件和警告由后端计算。不能创建订单或声称对账完成。"""
            manifest = await store.load_artifact(identity, "manifest_read")
            if not manifest:
                return json.dumps({"error": "必须先调用 inspect_intake_materials。"}, ensure_ascii=False)
            samples = await store.load_artifact(identity, "samples")
            required = any(f["included"] and f["mime_type"].startswith("image/") for f in manifest["files"])
            if required and samples is None:
                return json.dumps(
                    {"error": "必须先调用 inspect_intake_materials 完成抽查。"}, ensure_ascii=False
                )
            narrative = PrecheckNarrative(summary=summary, questions=questions, evidence_refs=evidence_refs)
            allowed = {f["id"] for f in manifest["files"]}
            if not set(evidence_refs) <= allowed:
                return json.dumps(
                    {"error": "引用必须是本会话的 files.id，不能写文件名。"}, ensure_ascii=False
                )
            cached = await store.load_artifact(identity, "candidate")
            if cached:
                return PrecheckNarrative.model_validate(cached["narrative"]).model_dump_json()
            async with sessions() as s:
                await store.job(s)
                item = await s.get(IntakeSession, intake_id)
                for fid, sample in (samples or {}).items():
                    f = await s.get(IntakeFile, fid)
                    if not f.user_classified:
                        f.category = sample["category"]
                await s.flush()
                checks = await service.inspect_materials(s, item, storage, samples)
                checks["samples"] = samples or {}
                checks["narrative"] = narrative.model_dump(mode="json")
                await s.commit()
            await store.save_artifact(identity, "candidate", checks, "candidate")
            return narrative.model_dump_json()

        cached = await store.load_artifact(identity, "candidate")
        if not cached:
            manifest = await store.load_artifact(identity, "manifest_read")
            samples = await store.load_artifact(identity, "samples")
            if not manifest or samples is None:
                for _correction in range(3):
                    try:
                        draft = await runner.generate(
                            "customer_service",
                            "对客户使用自然中文和文件名，不输出 UUID、工具名或字段名。ZIP 原包只作追溯，包内文件已纳入时不把原包未纳入说成缺失。你是下单前材料客服。必须实际调用 inspect_intake_materials 读取清单、CSV 检查并抽查图片，"
                            "然后仅说明服务启动条件和待补事项。不要完整识别票据、对账或创建订单。"
                            "不保证材料完整或账目正确。引用可为空，引用时只能用材料 id。",
                            PrecheckNarrative,
                            budget,
                            tools=[inspect_intake_materials],
                        )
                        await store.save_artifact(
                            identity,
                            "inspection_narrative",
                            draft.model_dump(mode="json"),
                            "inspection_narrative",
                        )
                    except AgentError:
                        if await store.load_artifact(identity, "stalled"):
                            raise
                        if (
                            not await store.load_artifact(identity, "manifest_read")
                            or await store.load_artifact(identity, "samples") is None
                        ):
                            raise
                    manifest = await store.load_artifact(identity, "manifest_read")
                    samples = await store.load_artifact(identity, "samples")
                    if manifest and samples is not None:
                        break
                if not manifest or samples is None:
                    raise AgentError("预检 Agent 没有取得真实检查工具成果。")
            for _correction in range(3):
                try:
                    await runner.generate(
                        "customer_service",
                        "对客户使用自然中文和文件名，不输出 UUID、工具名或字段名。ZIP 原包仅追溯不属于材料缺失。材料工具检查已真实完成。现在必须调用唯一工具 save_precheck_result 保存预检说明。"
                        "不能只返回文字而不保存。依据如下真实检查结果和抽查结果，说明缺失、重复和抽查范围。"
                        "不得声称已对账、已创建订单或保证材料齐全。引用可传空数组；引用仅使用 manifest.files.id。"
                        "工具成功返回的 JSON 就是最终结果，原样返回即可。\n"
                        + json.dumps(
                            {
                                "manifest": manifest,
                                "samples": samples,
                                "draft": await store.load_artifact(identity, "inspection_narrative"),
                            },
                            ensure_ascii=False,
                        ),
                        PrecheckNarrative,
                        budget,
                        tools=[save_precheck_result],
                    )
                except AgentError:
                    cached = await store.load_artifact(identity, "candidate")
                    if not cached:
                        raise
                    break
                cached = await store.load_artifact(identity, "candidate")
                if cached:
                    break
            if not cached:
                raise AgentError("预检 Agent 没有保存真实工具成果。")

        async with sessions() as s:
            job = await store.job(s)
            item = await s.get(IntakeSession, intake_id)
            job.result = cached
            job.status = "succeeded"
            job.lease_token = job.lease_expires_at = None
            item.status = (
                "needs_info"
                if cached["blockers"]
                else "ready_with_warnings"
                if cached["warnings"]
                else "ready"
            )
            narrative = cached["narrative"]
            content = "\n\n".join([narrative["summary"], *narrative["questions"]])
            await save_answer(s, item, job, content)
            await service.event(
                s, intake_id, "precheck.completed", {"revision": job.revision, "status": item.status}
            )
            await s.commit()
    except Exception as error:
        async with sessions() as s:
            job = await s.get(IntakeJob, job_id)
            if job and job.lease_token == token:
                item = await s.get(IntakeSession, intake_id)
                job.status = "failed"
                job.error = str(error) if isinstance(error, AgentError) else type(error).__name__
                job.lease_token = job.lease_expires_at = None
                if job.kind == "precheck":
                    item.status = "precheck_failed"
                await save_answer(
                    s,
                    item,
                    job,
                    "本次"
                    + ("材料预检" if kind == "precheck" else "接洽答复")
                    + "未完成，请重试或联系老板。",
                    status="failed",
                )
                await service.event(s, intake_id, "job.failed", {"job_id": job.id})
                await s.commit()
        if raise_errors:
            raise
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)
