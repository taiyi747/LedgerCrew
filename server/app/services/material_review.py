from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.integrations.agents.contracts import MaterialReviewOutput
from app.models import AgentTask


async def accepted_invoice_review(session: AsyncSession, order_id: str, file_id: str) -> AgentTask:
    tasks = (await session.scalars(select(AgentTask).where(
        AgentTask.order_id == order_id, AgentTask.task_type == "material_review")
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc()))).all()
    for task in tasks:
        if (task.input_data or {}).get("file_id") != file_id:
            continue
        if task.status != "succeeded" or not task.output_data:
            break
        result = MaterialReviewOutput.model_validate(task.output_data)
        if result.file_id == file_id and result.review_status == "ACCEPTED" and result.is_invoice:
            return task
        break
    raise AppError("invoice_review_required", "Latest material review must accept this invoice image", 409)
