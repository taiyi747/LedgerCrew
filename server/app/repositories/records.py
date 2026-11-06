from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BankTransaction, Order, StatementImport, StatementImportError, Studio, UploadedFile


async def get_studio(session: AsyncSession, studio_id: str) -> Studio | None:
    return await session.get(Studio, studio_id)


async def list_studios(session: AsyncSession, owner_user_id: str | None) -> list[Studio]:
    query = select(Studio)
    if owner_user_id is not None:
        query = query.where(Studio.owner_user_id == owner_user_id)
    return list((await session.scalars(query.order_by(Studio.created_at.desc()))).all())


async def get_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.get(Order, order_id)


async def list_orders(session: AsyncSession, owner_user_id: str | None) -> list[Order]:
    query = select(Order).join(Studio)
    if owner_user_id is not None:
        query = query.where(Studio.owner_user_id == owner_user_id)
    return list((await session.scalars(query.order_by(Order.created_at.desc()))).all())


async def get_file(session: AsyncSession, file_id: str) -> UploadedFile | None:
    return await session.get(UploadedFile, file_id)


async def list_files(session: AsyncSession, order_id: str) -> list[UploadedFile]:
    return list((await session.scalars(select(UploadedFile).where(UploadedFile.order_id == order_id).order_by(UploadedFile.created_at, UploadedFile.id))).all())


async def get_statement_import(session: AsyncSession, import_id: str) -> StatementImport | None:
    return await session.get(StatementImport, import_id)


async def get_import_for_file(session: AsyncSession, file_id: str) -> StatementImport | None:
    return (await session.scalars(select(StatementImport).where(StatementImport.uploaded_file_id == file_id))).first()


async def list_statement_imports(session: AsyncSession, order_id: str) -> list[StatementImport]:
    return list((await session.scalars(select(StatementImport).where(StatementImport.order_id == order_id).order_by(StatementImport.created_at, StatementImport.id))).all())


async def list_import_errors(session: AsyncSession, import_id: str) -> list[StatementImportError]:
    return list((await session.scalars(select(StatementImportError).where(StatementImportError.statement_import_id == import_id).order_by(StatementImportError.row_number))).all())


async def list_transactions(session: AsyncSession, order_id: str) -> list[BankTransaction]:
    return list((await session.scalars(select(BankTransaction).where(BankTransaction.order_id == order_id).order_by(BankTransaction.transaction_date, BankTransaction.id))).all())
