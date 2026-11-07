from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LedgerCrew API"
    frontend_origin: str = "http://127.0.0.1:3210"
    environment: Literal["development", "test", "production"] = "development"
    dev_owner_user_ids: list[str] = Field(default_factory=lambda: ["owner"])
    worker_enabled: bool = True
    admin_username: str = "owner"
    admin_password: SecretStr = SecretStr("junctionchina2026nb")
    database_url: str = "sqlite+aiosqlite:///./ledgercrew.db"
    sql_echo: bool = False
    storage_root: str = "./storage_data"
    max_upload_files: int = 20
    max_image_bytes: int = 5 * 1024 * 1024
    max_csv_bytes: int = 2 * 1024 * 1024
    max_archive_bytes: int = 25 * 1024 * 1024
    max_archive_files: int = 30
    max_archive_entry_bytes: int = 5 * 1024 * 1024
    max_archive_total_bytes: int = 50 * 1024 * 1024
    max_archive_ratio: int = 100
    csv_max_rows: int = 200
    csv_date_format: str = "%Y-%m-%d"
    sse_poll_seconds: float = Field(default=1.0, gt=0)
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)
    csv_column_map: dict[str, str] = Field(default_factory=lambda: {
        "transaction_date": "transaction_date",
        "counterparty": "counterparty",
        "direction": "direction",
        "amount": "amount",
        "description": "description",
        "external_id": "external_id",
    })


@lru_cache
def get_settings() -> Settings:
    return Settings()
