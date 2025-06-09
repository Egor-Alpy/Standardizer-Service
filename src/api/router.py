from fastapi import APIRouter
from src.api.endpoints import standardization, batch_standardization, tender_standardization

router = APIRouter()

router.include_router(
    standardization.router,
    prefix="/standardization",
    tags=["standardization"]
)

router.include_router(
    batch_standardization.router,
    prefix="/standardization",
    tags=["batch_standardization"]
)

router.include_router(
    tender_standardization.router,
    prefix="/standardization",
    tags=["tender_standardization"]
)