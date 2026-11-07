import csv
import hashlib
import io
import re
import stat
import zipfile
from pathlib import PurePosixPath, PureWindowsPath
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import AuditLog, UploadedFile
from app.repositories import records
from app.services import order_state
from app.services.access import file_for_user, order_for_user
from app.storage.base import Storage

CATEGORIES = {"invoice_image", "bank_statement_csv", "supporting_material"}


def check_category(category: str) -> None:
    if category not in CATEGORIES:
        raise AppError("invalid_file_category", "Unsupported file_category", 422)


def classify(filename: str, category: str, content: bytes) -> tuple[str, str]:
    ext = PurePosixPath(filename.lower()).suffix
    allowed = {"invoice_image": {".jpg", ".jpeg", ".png"}, "bank_statement_csv": {".csv"}, "supporting_material": {".jpg", ".jpeg", ".png"}}[category]
    if ext not in allowed:
        return "application/octet-stream", "unsupported"
    if ext in {".jpg", ".jpeg"}:
        expected_format, mime = "JPEG", "image/jpeg"
    elif ext == ".png":
        expected_format, mime = "PNG", "image/png"
    else:
        expected_format = None
    if expected_format is not None:
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format != expected_format:
                    return "application/octet-stream", "invalid"
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            return "application/octet-stream", "invalid"
        return mime, "valid"
    try:
        decoded = content.decode("utf-8-sig")
        if "\x00" in decoded or not decoded.strip():
            return "application/octet-stream", "invalid"
        first_row = next(csv.reader(io.StringIO(decoded)), [])
        if len(first_row) < 2:
            return "application/octet-stream", "invalid"
    except UnicodeDecodeError:
        return "application/octet-stream", "invalid"
    return "text/csv", "valid"


def limit_for(category: str, settings: Settings) -> int:
    return settings.max_csv_bytes if category == "bank_statement_csv" else settings.max_image_bytes


async def read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AppError("file_too_large", "File exceeds configured size limit", 413)
    return content


async def _save_record(
    session: AsyncSession, storage: Storage, order_id: str, filename: str, category: str,
    content: bytes, mime: str, status: str, source: str, principal: Principal,
    archive_id: str | None = None, entry_path: str | None = None,
) -> UploadedFile:
    file_id = str(uuid4())
    key = f"{order_id}/{file_id}"
    storage.put(key, content)
    record = UploadedFile(
        id=file_id, order_id=order_id, original_filename=filename[:255], file_category=category,
        storage_key=key, file_size=len(content), mime_type=mime,
        sha256=hashlib.sha256(content).hexdigest(), upload_source=source,
        validation_status=status, archive_file_id=archive_id, archive_entry_path=entry_path,
    )
    session.add(record)
    session.add(AuditLog(order_id=order_id, actor_type="customer", actor_id=principal.user_id, action="file.uploaded", entity_type="uploaded_file", entity_id=file_id, details={"status": status, "source": source}))
    return record


async def upload_files(
    session: AsyncSession, storage: Storage, order_id: str, category: str,
    uploads: list[UploadFile], principal: Principal, settings: Settings,
) -> list[UploadedFile]:
    await order_for_user(session, order_id, principal)
    check_category(category)
    if not uploads:
        raise AppError("missing_files", "At least one file is required", 422)
    if len(uploads) > settings.max_upload_files:
        raise AppError("upload_file_limit", "Too many files in one upload", 413)
    prepared = []
    request_size = 0
    for upload in uploads:
        filename = PureWindowsPath(upload.filename or "unnamed").name
        content = await read_upload(upload, limit_for(category, settings))
        request_size += len(content)
        if request_size > settings.max_upload_request_bytes:
            raise AppError("upload_request_too_large", "Upload request exceeds total size limit", 413)
        mime, status = classify(filename, category, content)
        prepared.append((filename, content, mime, status))
    result = []
    for filename, content, mime, status in prepared:
        result.append(await _save_record(session, storage, order_id, filename, category, content, mime, status, "direct", principal))
    await session.flush()
    await order_state.refresh_materials(session, order_id)
    await session.commit()
    return result


async def save_supporting_evidence(
    session: AsyncSession, storage: Storage, order_id: str, upload: UploadFile,
    principal: Principal, settings: Settings,
) -> UploadedFile:
    """Save one validated evidence image in the caller's transaction."""
    filename = PureWindowsPath(upload.filename or "unnamed").name
    content = await read_upload(upload, settings.max_image_bytes)
    mime, status = classify(filename, "supporting_material", content)
    if status != "valid":
        raise AppError("invalid_evidence_file", "Evidence must be a valid JPG or PNG image", 422)
    return await _save_record(session, storage, order_id, filename, "supporting_material",
                              content, mime, status, "direct", principal)


def _safe_entry(info: zipfile.ZipInfo) -> bool:
    path = info.filename
    normalized = path.replace("\\", "/")
    checked = normalized[:-1] if info.is_dir() and normalized.endswith("/") else normalized
    parts = PurePosixPath(checked).parts
    if not parts or normalized.startswith("/") or PureWindowsPath(path).is_absolute() or re.match(r"^[A-Za-z]:", path):
        return False
    if any(part in {"", ".", ".."} for part in checked.split("/")):
        return False
    if len(parts) > 2:
        return False
    return not stat.S_ISLNK(info.external_attr >> 16)


def inspect_archive(content: bytes, settings: Settings) -> list[tuple[zipfile.ZipInfo, bytes]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            all_infos = archive.infolist()
            if any(not _safe_entry(info) for info in all_infos):
                raise AppError("unsafe_archive_path", "Archive contains an unsafe path or link", 422)
            infos = [info for info in all_infos if not info.is_dir()]
            if len(infos) > settings.max_archive_files:
                raise AppError("archive_file_limit", "Archive contains too many files", 413)
            total = 0
            for info in infos:
                if PurePosixPath(info.filename.lower()).suffix == ".zip":
                    raise AppError("nested_archive", "Nested ZIP files are not supported", 422)
                if info.file_size > settings.max_archive_entry_bytes:
                    raise AppError("archive_entry_too_large", "Archive entry exceeds size limit", 413)
                total += info.file_size
                if total > settings.max_archive_total_bytes:
                    raise AppError("archive_total_too_large", "Archive exceeds total size limit", 413)
                if info.file_size and (info.compress_size == 0 or info.file_size > info.compress_size * settings.max_archive_ratio):
                    raise AppError("archive_ratio_exceeded", "Archive compression ratio exceeds limit", 413)
            extracted = []
            actual_total = 0
            for info in infos:
                with archive.open(info) as source:
                    data = source.read(settings.max_archive_entry_bytes + 1)
                if len(data) > settings.max_archive_entry_bytes:
                    raise AppError("archive_entry_too_large", "Archive entry exceeds size limit", 413)
                actual_total += len(data)
                if actual_total > settings.max_archive_total_bytes:
                    raise AppError("archive_total_too_large", "Archive exceeds total size limit", 413)
                if data.startswith(b"PK\x03\x04"):
                    raise AppError("nested_archive", "Nested ZIP files are not supported", 422)
                extracted.append((info, data))
            return extracted
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise AppError("corrupt_archive", "Archive is corrupt", 422) from exc


async def upload_archive(
    session: AsyncSession, storage: Storage, order_id: str, category: str,
    upload: UploadFile, principal: Principal, settings: Settings,
) -> tuple[UploadedFile, list[UploadedFile]]:
    await order_for_user(session, order_id, principal)
    check_category(category)
    content = await read_upload(upload, settings.max_archive_bytes)
    previous_archive_bytes = await session.scalar(select(func.coalesce(func.sum(UploadedFile.file_size), 0)).where(
        UploadedFile.order_id == order_id, UploadedFile.file_category == "archive"))
    if previous_archive_bytes + len(content) > settings.max_order_archive_bytes:
        raise AppError("order_archive_quota", "Order archive quota exceeded", 413)
    name = PureWindowsPath(upload.filename or "archive.zip").name
    if PurePosixPath(name.lower()).suffix != ".zip":
        raise AppError("unsupported_archive", "A ZIP file is required", 415)
    archive_record = await _save_record(session, storage, order_id, name, "archive", content, "application/zip", "pending_review", "direct", principal)
    await session.commit()
    try:
        extracted = inspect_archive(content, settings)
        previous_extracted_bytes = await session.scalar(select(func.coalesce(func.sum(UploadedFile.file_size), 0)).where(
            UploadedFile.order_id == order_id, UploadedFile.upload_source == "archive"))
        if previous_extracted_bytes + sum(len(data) for _, data in extracted) > settings.max_order_extracted_bytes:
            raise AppError("order_extracted_quota", "Order extracted file quota exceeded", 413)
        if any(len(data) > limit_for(category, settings) for _, data in extracted):
            raise AppError("archive_entry_too_large", "Archive entry exceeds category size limit", 413)
        entries = []
        for info, data in extracted:
            filename = PurePosixPath(info.filename.replace("\\", "/")).name
            mime, status = classify(filename, category, data)
            entries.append(await _save_record(session, storage, order_id, filename, category, data, mime, status, "archive", principal, archive_record.id, info.filename))
        archive_record.validation_status = "valid"
        await session.flush()
        await order_state.refresh_materials(session, order_id)
        session.add(AuditLog(order_id=order_id, actor_type="system", action="archive.validated", entity_type="uploaded_file", entity_id=archive_record.id, details={"entry_count": len(entries)}))
        await session.commit()
        return archive_record, entries
    except AppError as exc:
        await session.rollback()
        archive_record = await session.get(UploadedFile, archive_record.id)
        archive_record.validation_status = "invalid"
        session.add(AuditLog(order_id=order_id, actor_type="system", action="archive.rejected", entity_type="uploaded_file", entity_id=archive_record.id, details={"reason": exc.code}))
        await session.commit()
        raise


async def list_files(session: AsyncSession, order_id: str, principal: Principal) -> list[UploadedFile]:
    await order_for_user(session, order_id, principal)
    return await records.list_files(session, order_id)


async def get_file(session: AsyncSession, file_id: str, principal: Principal) -> UploadedFile:
    return await file_for_user(session, file_id, principal)
