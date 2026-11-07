from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_reviews,
    auth,
    events,
    exceptions,
    feedback,
    files,
    imports,
    orders,
    payments,
    reconciliation,
    reports,
    studios,
    worker_tasks,
    workflows,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(agent_reviews.router)
api_router.include_router(worker_tasks.router)
api_router.include_router(workflows.router)
api_router.include_router(studios.router)
api_router.include_router(feedback.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(files.router)
api_router.include_router(imports.router)
api_router.include_router(reconciliation.router)
api_router.include_router(events.router)
api_router.include_router(exceptions.router)
api_router.include_router(reports.router)
