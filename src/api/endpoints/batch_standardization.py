from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
import uuid
import logging
from datetime import datetime

from src.api.dependencies import verify_api_key
from src.services.ai_standardizer import AIStandardizer
from src.models.batch import (
    BatchStandardizationRequest,
    BatchStandardizationResponse,
    StandardizedProductResponse
)
from src.models.standardization import ProductForStandardization, ProductAttribute

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/batch/standardize", response_model=BatchStandardizationResponse)
async def standardize_products_batch(
        request: BatchStandardizationRequest,
        api_key: str = Depends(verify_api_key)
):
    """
    Стандартизировать пачку классифицированных товаров.
    Принимает результат из сервиса классификации.
    """
    batch_id = f"std_batch_{uuid.uuid4().hex[:8]}"
    logger.info(f"Starting batch standardization {batch_id} for {len(request.classified_products)} products")

    try:
        # Инициализируем AI стандартизатор
        ai_standardizer = AIStandardizer()

        # Подготавливаем товары для стандартизации
        products_for_standardization = []

        for product in request.classified_products:
            # Проверяем наличие кода ОКПД2
            if not product.okpd2_code:
                logger.warning(f"Product {product.id} has no OKPD2 code, skipping")
                continue

            # Преобразуем в модель для стандартизации
            attributes = [
                ProductAttribute(
                    attr_name=attr.attr_name,
                    attr_value=attr.attr_value
                )
                for attr in product.attributes
            ]

            product_for_std = ProductForStandardization(
                id=product.id,
                source_id=product.id,  # В данном случае используем тот же ID как source_id
                source_collection="batch_input",  # Фиктивное имя коллекции для batch
                title=product.title,
                okpd2_code=product.okpd2_code,
                attributes=attributes
            )

            products_for_standardization.append(product_for_std)

        if not products_for_standardization:
            logger.warning("No products with OKPD2 codes for standardization")
            return BatchStandardizationResponse(
                batch_id=batch_id,
                total_products=len(request.classified_products),
                standardized_products=[],
                standardized_count=0,
                failed_count=len(request.classified_products)
            )

        # Отправляем на стандартизацию
        standardization_results = await ai_standardizer.standardize_batch(products_for_standardization)

        # Собираем результаты
        standardized_products = []

        for product in request.classified_products:
            if product.id in standardization_results:
                standardized_attrs = standardization_results[product.id]

                standardized_product = StandardizedProductResponse(
                    id=product.id,
                    title=product.title,
                    okpd2_code=product.okpd2_code,
                    okpd2_name=product.okpd2_name,
                    okpd_groups=product.okpd_groups,
                    original_attributes=product.attributes,
                    standardized_attributes=standardized_attrs
                )

                standardized_products.append(standardized_product)

        logger.info(
            f"Batch {batch_id} completed: "
            f"{len(standardized_products)} products standardized"
        )

        await ai_standardizer.close()

        return BatchStandardizationResponse(
            batch_id=batch_id,
            total_products=len(request.classified_products),
            standardized_products=standardized_products,
            standardized_count=len(standardized_products),
            failed_count=len(request.classified_products) - len(standardized_products)
        )

    except Exception as e:
        logger.error(f"Error in batch standardization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))