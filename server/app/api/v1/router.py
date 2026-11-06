from fastapi import APIRouter
from app.api.v1.endpoints import files, imports, orders, reconciliation, studios

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(studios.router)
api_router.include_router(orders.router)
api_router.include_router(files.router)
api_router.include_router(imports.router)
api_router.include_router(reconciliation.router)
