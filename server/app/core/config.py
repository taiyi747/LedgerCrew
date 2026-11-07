from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DevAuthAccount(BaseModel):
    """开发/测试模拟账号（fixture 级），生产认证不读取本配置。"""

    email: str = Field(min_length=3, max_length=254)
    user_id: str = Field(min_length=1, max_length=100)
    password: SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LedgerCrew API"
    environment: Literal["development", "test", "production"] = "development"
    dev_owner_user_ids: list[str] = Field(default_factory=lambda: ["owner"])
    dev_auth_accounts: list[DevAuthAccount] = Field(default_factory=lambda: [
        DevAuthAccount(email="demo@example.com", user_id="demo", password=SecretStr("example-password")),
    ])
    dev_auth_credential_ttl_seconds: int = Field(default=3600, gt=0)
    auth_session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    auth_max_failed_attempts: int = Field(default=5, ge=2, le=20)
    auth_lock_seconds: int = Field(default=900, ge=60, le=86400)
    service_prices_cents: dict[str, int] = Field(default_factory=dict)
    service_currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_sandbox_webhook_secret: SecretStr | None = None
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_timeout_seconds: int = Field(default=900, ge=30, le=86400)
    worker_lease_seconds: int = Field(default=60, ge=10, le=600)
    worker_heartbeat_seconds: int = Field(default=10, ge=1, le=120)
    api_rate_limit_requests: int = Field(default=1000, ge=1)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1)
    sse_max_connections: int = Field(default=20, ge=1)
    database_url: str = "sqlite+aiosqlite:///./ledgercrew.db"
    sql_echo: bool = False
    storage_root: str = "./storage_data"
    max_upload_files: int = 20
    max_upload_request_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_image_bytes: int = 5 * 1024 * 1024
    max_csv_bytes: int = 2 * 1024 * 1024
    max_archive_bytes: int = 25 * 1024 * 1024
    max_archive_files: int = 30
    max_archive_entry_bytes: int = 5 * 1024 * 1024
    max_archive_total_bytes: int = 50 * 1024 * 1024
    max_archive_ratio: int = 100
    max_order_archive_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_order_extracted_bytes: int = Field(default=200 * 1024 * 1024, gt=0)
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
