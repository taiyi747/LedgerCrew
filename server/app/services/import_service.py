from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import AuditLog, BankTransaction, StatementImport, StatementImportError
from app.repositories import records
from app.schemas.transaction import CSVImportCreate, StatementImportRead
from app.services.access import file_for_user, order_for_user
from app.services.csv_service import CSVService
from app.storage.base import Storage


async def _read_import(session: AsyncSession, statement_import: StatementImport) -> StatementImportRead:
    return StatementImportRead.model_validate({
        "id": statement_import.id,
        "order_id": statement_import.order_id,
        "uploaded_file_id": statement_import.uploaded_file_id,
        "status": statement_import.status,
        "total_rows": statement_import.total_rows,
        "success_rows": statement_import.success_rows,
        "failed_rows": statement_import.failed_rows,
        "column_map_json": statement_import.column_map_json,
        "created_at": statement_import.created_at,
        "errors": await records.list_import_errors(session, statement_import.id),
    })


async def import_csv(
    session: AsyncSession, storage: Storage, order_id: str, data: CSVImportCreate,
    principal: Principal, settings: Settings,
) -> StatementImportRead:
    await order_for_user(session, order_id, principal)
    file = await file_for_user(session, data.file_id, principal)
    if file.order_id != order_id or file.file_category != "bank_statement_csv" or file.validation_status == "unsupported":
        raise AppError("invalid_statement_file", "A CSV file from this order is required", 422)
    existing = await records.get_import_for_file(session, file.id)
    if existing is not None:
        return await _read_import(session, existing)

    column_map = settings.csv_column_map | (data.column_map or {})
    parsed = CSVService(column_map, settings.csv_date_format, settings.csv_max_rows).parse(storage.read(file.storage_key))
    statement_import = StatementImport(
        order_id=order_id, uploaded_file_id=file.id, status="completed", total_rows=parsed.total_rows,
        success_rows=len(parsed.transactions), failed_rows=len(parsed.errors), column_map_json=column_map,
    )
    session.add(statement_import)
    await session.flush()
    for row in parsed.transactions:
        session.add(BankTransaction(
            order_id=order_id, statement_import_id=statement_import.id, row_number=row.row_number,
            external_id=row.external_id, transaction_date=row.transaction_date,
            counterparty=row.counterparty, normalized_counterparty=row.normalized_counterparty,
            direction=row.direction, amount_cents=row.amount_cents, description=row.description,
            raw_row_json=row.raw_row_json,
        ))
    for error in parsed.errors:
        session.add(StatementImportError(
            statement_import_id=statement_import.id, row_number=error.row_number,
            reason=error.reason, raw_row_json=error.raw_row_json,
        ))
    session.add(AuditLog(
        order_id=order_id, actor_type="customer", actor_id=principal.user_id,
        action="statement.imported", entity_type="statement_import", entity_id=statement_import.id,
        details={"total_rows": parsed.total_rows, "success_rows": len(parsed.transactions), "failed_rows": len(parsed.errors)},
    ))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await records.get_import_for_file(session, file.id)
        if existing is None:
            raise
        return await _read_import(session, existing)
    return await _read_import(session, statement_import)


async def get_import(session: AsyncSession, import_id: str, principal: Principal) -> StatementImportRead:
    statement_import = await records.get_statement_import(session, import_id)
    if statement_import is None:
        raise AppError("not_found", "Import not found", 404)
    await order_for_user(session, statement_import.order_id, principal)
    return await _read_import(session, statement_import)


async def list_imports(session: AsyncSession, order_id: str, principal: Principal) -> list[StatementImportRead]:
    await order_for_user(session, order_id, principal)
    return [await _read_import(session, item) for item in await records.list_statement_imports(session, order_id)]


async def list_transactions(session: AsyncSession, order_id: str, principal: Principal) -> list[BankTransaction]:
    await order_for_user(session, order_id, principal)
    return await records.list_transactions(session, order_id)
