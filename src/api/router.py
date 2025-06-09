from fastapi import APIRouter
from src.api.endpoints import standardization, batch_standardization

router = APIRouter()

router.include_router(
    standardization.router,
    prefix="/standardization",
    tags=["standardization"]
)

# НОВОЕ: добавляем роутер для batch обработки
router.include_router(
    batch_standardization.router,
    prefix="/standardization",
    tags=["batch_standardization"]
)