from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankTransaction,
    ExceptionTicket,
    InvoiceRecord,
    ReconciliationBatch,
    ReconciliationMatch,
    UploadedFile,
)


async def list_invoices(session: AsyncSession, order_id: str) -> list[InvoiceRecord]:
    return list((await session.scalars(select(InvoiceRecord).where(InvoiceRecord.order_id == order_id)
                                       .order_by(InvoiceRecord.created_at, InvoiceRecord.id))).all())


async def list_transactions(session: AsyncSession, order_id: str) -> list[BankTransaction]:
    return list((await session.scalars(select(BankTransaction).where(BankTransaction.order_id == order_id)
                                       .order_by(BankTransaction.created_at, BankTransaction.id))).all())


async def invoice_file_hashes(session: AsyncSession, order_id: str) -> dict[str, str]:
    rows = (await session.execute(select(UploadedFile.id, UploadedFile.sha256)
                                  .where(UploadedFile.order_id == order_id))).all()
    return dict(rows)


async def next_batch_number(session: AsyncSession, order_id: str) -> int:
    value = await session.scalar(select(func.max(ReconciliationBatch.batch_number))
                                 .where(ReconciliationBatch.order_id == order_id))
    return (value or 0) + 1


async def latest_batch(session: AsyncSession, order_id: str) -> ReconciliationBatch | None:
    return (await session.scalars(select(ReconciliationBatch).where(ReconciliationBatch.order_id == order_id)
                                  .order_by(ReconciliationBatch.batch_number.desc()).limit(1))).first()


async def list_matches(session: AsyncSession, batch_id: str) -> list[ReconciliationMatch]:
    return list((await session.scalars(select(ReconciliationMatch).where(ReconciliationMatch.batch_id == batch_id)
                                       .order_by(ReconciliationMatch.created_at, ReconciliationMatch.id))).all())


async def list_tickets(session: AsyncSession, batch_id: str) -> list[ExceptionTicket]:
    return list((await session.scalars(select(ExceptionTicket).where(ExceptionTicket.batch_id == batch_id)
                                       .order_by(ExceptionTicket.created_at, ExceptionTicket.id))).all())
