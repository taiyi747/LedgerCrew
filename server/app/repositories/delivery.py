from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExceptionDecision, ExceptionSupplement, ReportReviewAction, ReportVersion


async def list_supplements(session: AsyncSession, exception_id: str) -> list[ExceptionSupplement]:
    return list((await session.scalars(select(ExceptionSupplement).where(ExceptionSupplement.exception_id == exception_id)
                                       .order_by(ExceptionSupplement.created_at, ExceptionSupplement.id))).all())


async def list_decisions(session: AsyncSession, exception_id: str) -> list[ExceptionDecision]:
    return list((await session.scalars(select(ExceptionDecision).where(ExceptionDecision.exception_id == exception_id)
                                       .order_by(ExceptionDecision.created_at, ExceptionDecision.id))).all())


async def list_reports(session: AsyncSession, order_id: str) -> list[ReportVersion]:
    return list((await session.scalars(select(ReportVersion).where(ReportVersion.order_id == order_id)
                                       .order_by(ReportVersion.version.desc()))).all())


async def next_report_version(session: AsyncSession, order_id: str) -> int:
    value = await session.scalar(select(func.max(ReportVersion.version)).where(ReportVersion.order_id == order_id))
    return (value or 0) + 1


async def report_from_task(session: AsyncSession, task_id: str) -> ReportVersion | None:
    return (await session.scalars(select(ReportVersion).where(ReportVersion.source_task_id == task_id))).first()


async def approval_for_report(session: AsyncSession, report_id: str) -> ReportReviewAction | None:
    return (await session.scalars(select(ReportReviewAction).where(
        ReportReviewAction.report_id == report_id, ReportReviewAction.action == "approved")
        .order_by(ReportReviewAction.created_at.desc()))).first()
