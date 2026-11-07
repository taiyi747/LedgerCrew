from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.limits import RequestRateLimiter, SSEConnectionLimiter
from app.db.session import get_session
from app.services.health_service import readiness


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0")
    register_exception_handlers(app)
    app.state.request_rate_limiter = RequestRateLimiter()
    app.state.sse_connection_limiter = SSEConnectionLimiter()

    @app.middleware("http")
    async def limit_requests(request: Request, call_next):
        if request.url.path.startswith("/api/v1/"):
            client_host = request.client.host if request.client else "unknown"
            if not await app.state.request_rate_limiter.allow(client_host, get_settings()):
                return JSONResponse(status_code=429, content={
                    "error": {"code": "rate_limited", "message": "Request rate limit exceeded"}})
        return await call_next(request)

    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready(session: AsyncSession = Depends(get_session)) -> JSONResponse:
        status_code, payload = await readiness(session)
        return JSONResponse(status_code=status_code, content=payload)

    return app


app = create_app()
