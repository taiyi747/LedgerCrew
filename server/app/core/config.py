from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DevAuthAccount(BaseModel):
    """开发/测试模拟账号（fixture 级），禁止用于生产。

    这里没有密码哈希方案：真实凭证存储与密码哈希属于 DEC-013 确认后的正式安全方案。
    生产环境的认证提供者不读取本配置（见 ``app/core/security.py``）。
    """

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
