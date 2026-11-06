from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LedgerCrew API"
    environment: Literal["development", "test", "production"] = "development"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
