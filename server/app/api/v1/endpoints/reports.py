from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.models import Order, Studio
from app.schemas.delivery import ReportReviewRequest, ReportVersionRead
from app.services import export_service, report_service

router = APIRouter(tags=["reports"])


@router.get("/orders/{order_id}/reports", response_model=list[ReportVersionRead])
async def list_reports(order_id: str, session: AsyncSession = Depends(get_session),
                       principal: Principal = Depends(get_current_principal)):
    return await report_service.list_reports(session, order_id, principal)


@router.get("/reports/{report_id}", response_model=ReportVersionRead)
async def get_report(report_id: str, session: AsyncSession = Depends(get_session),
                     principal: Principal = Depends(get_current_principal)):
    return await report_service.get_report(session, report_id, principal)


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str, session: AsyncSession = Depends(get_session),
                          principal: Principal = Depends(get_current_principal)):
    """交付下载：可打印 HTML 报告。"""
    report = await report_service.get_report(session, report_id, principal)
    order = await session.get(Order, report.order_id)
    studio = await session.get(Studio, order.studio_id) if order else None
    context = {
        "studio_name": studio.name if studio else None,
        "period": f"{order.period_start} — {order.period_end}" if order and order.period_start else None,
    }
    filename = quote(f"小账房-账目核对报告-v{report.version}.html")
    return Response(report_service.printable_html(report, **context), media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})


@router.post("/reports/{report_id}/submit-review", response_model=ReportVersionRead)
async def submit_review(report_id: str, session: AsyncSession = Depends(get_session),
                        principal: Principal = Depends(get_current_principal)):
    return await report_service.submit_review(session, report_id, principal)


@router.post("/reports/{report_id}/approve", response_model=ReportVersionRead)
async def approve(report_id: str, data: ReportReviewRequest | None = None,
                  session: AsyncSession = Depends(get_session),
                  principal: Principal = Depends(get_current_principal)):
    return await report_service.approve(session, report_id, principal, data.reason if data else None)


@router.post("/reports/{report_id}/reject", response_model=ReportVersionRead)
async def reject(report_id: str, data: ReportReviewRequest,
                 session: AsyncSession = Depends(get_session),
                 principal: Principal = Depends(get_current_principal)):
    return await report_service.reject(session, report_id, principal, data.reason or "")


@router.post("/reports/{report_id}/publish", response_model=ReportVersionRead)
async def publish(report_id: str, session: AsyncSession = Depends(get_session),
                  principal: Principal = Depends(get_current_principal)):
    return await report_service.publish(session, report_id, principal)


@router.get("/orders/{order_id}/exports/{export_type}.csv")
async def export_csv(order_id: str, export_type: str, session: AsyncSession = Depends(get_session),
                     principal: Principal = Depends(get_current_principal)):
    content = await export_service.export_csv(session, order_id, export_type, principal)
    return Response(content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ledgercrew-{export_type}.csv"'})
