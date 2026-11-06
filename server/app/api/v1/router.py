from fastapi import APIRouter
from app.api.v1.endpoints import files, orders, studios

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(studios.router)
api_router.include_router(orders.router)
api_router.include_router(files.router)
