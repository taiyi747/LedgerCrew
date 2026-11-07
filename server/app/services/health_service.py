"""Readiness checks that report observed dependencies without exposing configuration."""

import logging
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def readiness(session: AsyncSession) -> tuple[int, dict]:
    components: dict[str, object] = {
        "api": "ok",
        "database": "unavailable",
        "worker": "heartbeat_unverified",
        "task_queue": "unavailable",
        "cache": "not_configured",
        "external_ai": "unconfigured",
        "workflow": "unavailable",
        "business_services": "degraded",
    }
    try:
        await session.execute(text("SELECT 1"))
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        if revision != "0016_workflow_provenance":
            components["database"] = "migration_required"
            return 503, {"status": "not_ready", "components": components}
        components["database"] = "ok"
        counts = dict((await session.execute(text(
            "SELECT status, count(*) FROM agent_tasks GROUP BY status"))).all())
        components["task_queue"] = {"status": "ok", **{
            state: counts.get(state, 0) for state in
            ("queued", "running", "retrying", "failed", "timeout", "cancelled")}}
        from app.core.config import get_settings
        from app.db.types import utc_now
        from app.models import WorkerInstance

        recent = utc_now() - timedelta(seconds=get_settings().worker_lease_seconds)
        active_workers = await session.scalar(select(func.count()).select_from(WorkerInstance).where(
            WorkerInstance.status == "running", WorkerInstance.last_heartbeat_at >= recent))
        components["worker"] = {"status": "active" if active_workers else "unavailable",
                                "active_count": active_workers or 0}
        components["workflow"] = "configured"
    except (SQLAlchemyError, OSError):
        logger.exception("Readiness database check failed")
        return 503, {"status": "not_ready", "components": components}
    from app.agents.config import Settings as MiMoSettings
    from app.agents.errors import ConfigurationError

    try:
        MiMoSettings.from_env()
        components["external_ai"] = "configured_unverified"
    except (ConfigurationError, ValidationError, ValueError):
        components["external_ai"] = "unconfigured"
    # A configured key and a worker heartbeat cannot prove the external model is reachable.
    return 503, {"status": "not_ready", "components": components}
