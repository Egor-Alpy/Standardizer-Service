from fastapi import APIRouter
from src.api.endpoints import standardization

router = APIRouter()

router.include_router(
    standardization.router,
    prefix="/standardization",
    tags=["standardization"]
)
