from fastapi import FastAPI

from app.api.v1.router import api_router
from app.live.api import router as live_router, assets as owner_assets
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0")
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(live_router)
    app.include_router(owner_assets)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
