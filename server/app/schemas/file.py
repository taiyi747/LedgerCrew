from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    original_filename: str
    file_category: str
    file_size: int
    mime_type: str
    sha256: str
    upload_source: str
    validation_status: str
    archive_file_id: str | None
    archive_entry_path: str | None
    created_at: datetime


class FileBatchRead(BaseModel):
    files: list[FileRead]


class ArchiveRead(BaseModel):
    archive: FileRead
    entries: list[FileRead]
