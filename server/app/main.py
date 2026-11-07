import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.intake.api import router as intake_router

from app.api.v1.router import api_router
from app.live.api import router as live_router, assets as owner_assets
from app.live.worker import worker as worker_loop
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import make_engine
from app.services import auth_service

logger = logging.getLogger(__name__)


async def _run_worker() -> None:
    """Keep the queue poller alive for the lifetime of the API process."""
    try:
        await worker_loop()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Worker stopped; queued jobs will not progress until it is restarted")


async def _bootstrap_admin(settings) -> None:
    password = settings.admin_password.get_secret_value()
    if not password:
        return
    engine = make_engine(settings.database_url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            await auth_service.ensure_admin(session, settings.admin_username, password)
    except Exception:  # an unmigrated database must not block startup
        logger.warning("Administrator bootstrap skipped; has the database been migrated?", exc_info=True)
    finally:
        await engine.dispose()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await _bootstrap_admin(settings)

    task: asyncio.Task | None = None
    if settings.worker_enabled:
        task = asyncio.create_task(_run_worker(), name="ledgercrew-worker")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(intake_router)
    app.include_router(live_router)
    app.include_router(owner_assets)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
