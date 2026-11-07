from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr

from .contracts import DataModel
from .errors import ConfigurationError


class Settings(DataModel):
    api_key: SecretStr = Field(repr=False)
    base_url: str = "https://api.xiaomimimo.com/v1"
    model_pro: str = "mimo-v2.6-pro"
    model_flash: str = "mimo-v2.6-flash"
    timeout_seconds: float = Field(default=60, gt=0)
    transient_retries: int = Field(default=2, ge=0, le=2)
    output_retries: int = Field(default=2, ge=0, le=2)
    max_requests: int = Field(default=64, ge=1)
    # Per-conversation tool-loop caps. The persisted RequestBudget is the real
    # cost bound (every model request reserves against it), so these only stop a
    # single conversation from looping; keep them generous so plan-then-work
    # turns and large batches orchestrated inside one tool call are never cut.
    max_function_calls: int = Field(default=300, ge=1)
    max_iterations: int = Field(default=300, ge=1)
    data_dir: Path = Path("data")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        load_dotenv(env_file or Path(__file__).resolve().parents[2] / ".env", override=False)
        key = os.environ.get("MIMO_API_KEY", "")
        if not key or key == "replace-with-your-key":
            raise ConfigurationError("请在本地 server/.env 配置 MIMO_API_KEY。")
        return cls(
            api_key=SecretStr(key),
            base_url=os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"),
            model_pro=os.environ.get("MIMO_MODEL_PRO", "mimo-v2.6-pro"),
            model_flash=os.environ.get("MIMO_MODEL_FLASH", "mimo-v2.6-flash"),
            timeout_seconds=float(os.environ.get("MIMO_TIMEOUT_SECONDS", "60")),
            transient_retries=int(os.environ.get("MIMO_TRANSIENT_RETRIES", "2")),
            output_retries=int(os.environ.get("MIMO_OUTPUT_RETRIES", "2")),
            max_requests=int(os.environ.get("MIMO_MAX_REQUESTS", "64")),
            max_function_calls=int(os.environ.get("MIMO_MAX_FUNCTION_CALLS", "300")),
            max_iterations=int(os.environ.get("MIMO_MAX_ITERATIONS", "300")),
            data_dir=Path(os.environ.get("LEDGERCREW_DATA_DIR", "data")),
        )
