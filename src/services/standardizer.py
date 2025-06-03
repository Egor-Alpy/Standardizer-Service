import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.services.ai_standardizer import AIStandardizer
from src.services.product_fetcher import ProductFetcher
from src.storage.classified_mongo import ClassifiedMongoStore
from src.storage.standardized_mongo import StandardizedMongoStore
from src.models.standardization import (
    ProductForStandardization,
    StandardizedProduct,
    StandardizationStatus,
    ProductAttribute
)

logger = logging.getLogger(__name__)


class StandardizationService:
    """Основной сервис стандартизации товаров"""

    def __init__(
            self,
            classified_store: ClassifiedMongoStore,
            standardized_store: StandardizedMongoStore,
            product_fetcher: ProductFetcher,
            batch_size: int = 50,
            worker_id: str = None
    ):
        self.classified_store = classified_store
        self.standardized_store = standardized_store
        self.product_fetcher = product_fetcher
        self.batch_size = batch_size
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"

        # AI стандартизатор
        self.ai_standardizer = AIStandardizer()

        logger.info(f"Standardization service initialized with batch_size={batch_size}")

    async def process_batch(
            self,
            okpd_prefix: Optional[str] = None
    ) -> Dict[str, Any]:
        """Обработать батч товаров"""
        batch_id = f"std_batch_{uuid.uuid4().hex[:8]}"
        logger.info(f"Processing batch {batch_id}")

        try:
            # 1. Получаем товары для стандартизации
            classified_products = await self.classified_store.get_products_for_standardization(
                limit=self.batch_size,
                okpd_prefix=okpd_prefix
            )

            if not classified_products:
                logger.info("No products to standardize")
                return {
                    "batch_id": batch_id,
                    "total": 0,
                    "standardized": 0,
                    "failed": 0
                }

            logger.info(f"Found {len(classified_products)} products to standardize")

            # 2. Подготавливаем товары для стандартизации
            products_for_ai = []
            product_map = {}  # Для быстрого доступа по ID

            for classified_product in classified_products:
                # Получаем полную информацию о товаре из исходной БД
                full_product = await self.product_fetcher.fetch_product_details(
                    classified_product["old_mongo_id"],
                    classified_product["collection_name"]  # Передаем имя коллекции
                )

                if not full_product:
                    logger.warning(f"Product not found in source: {classified_product['old_mongo_id']}")
                    continue

                # Создаем модель для AI
                attributes = [
                    ProductAttribute(
                        attr_name=attr.get("attr_name", ""),
                        attr_value=attr.get("attr_value", "")
                    )
                    for attr in full_product.get("attributes", [])
                ]

                product_for_ai = ProductForStandardization(
                    id=str(classified_product["_id"]),  # Передаем как id
                    old_mongo_id=classified_product["old_mongo_id"],
                    collection_name=classified_product["collection_name"],
                    title=full_product.get("title", ""),
                    okpd2_code=classified_product["okpd2_code"],
                    attributes=attributes
                )

                products_for_ai.append(product_for_ai)
                product_map[str(classified_product["_id"])] = {
                    "classified": classified_product,
                    "full": full_product
                }

            if not products_for_ai:
                logger.warning("No valid products for standardization")
                return {
                    "batch_id": batch_id,
                    "total": len(classified_products),
                    "standardized": 0,
                    "failed": len(classified_products)
                }

            # 3. Отправляем в AI для стандартизации
            logger.info(f"Sending {len(products_for_ai)} products to AI standardizer")
            standardization_results = await self.ai_standardizer.standardize_batch(products_for_ai)

            # 4. Обрабатываем результаты
            standardized_count = 0
            failed_count = 0
            standardized_products = []
            status_updates = []

            for product_id, product_data in product_map.items():
                classified = product_data["classified"]
                full = product_data["full"]

                if product_id in standardization_results:
                    # Успешная стандартизация
                    standardized_attrs = standardization_results[product_id]

                    # Создаем стандартизированный товар
                    standardized_product = StandardizedProduct(
                        # Идентификаторы
                        old_mongo_id=classified["old_mongo_id"],
                        classified_mongo_id=str(classified["_id"]),
                        collection_name=classified["collection_name"],

                        # Основные данные
                        title=full.get("title", ""),
                        description=full.get("description"),
                        article=full.get("article"),
                        brand=full.get("brand"),
                        country_of_origin=full.get("country_of_origin"),
                        warranty_months=full.get("warranty_months"),
                        category=full.get("category"),
                        created_at=full.get("created_at"),

                        # Классификация
                        okpd2_code=classified["okpd2_code"],
                        okpd2_name=classified.get("okpd2_name", ""),
                        okpd_group=classified.get("okpd_group", []),

                        # Атрибуты
                        original_attributes=[
                            ProductAttribute(
                                attr_name=attr.get("attr_name", ""),
                                attr_value=attr.get("attr_value", "")
                            )
                            for attr in full.get("attributes", [])
                        ],
                        standardized_attributes=standardized_attrs,

                        # Поставщики
                        suppliers=full.get("suppliers", []),

                        # Метаданные
                        standardization_status=StandardizationStatus.STANDARDIZED,
                        standardization_completed_at=datetime.utcnow(),
                        standardization_batch_id=batch_id,
                        standardization_worker_id=self.worker_id
                    )

                    standardized_products.append(standardized_product)
                    standardized_count += 1

                    # Обновляем статус в классифицированной БД
                    status_updates.append({
                        "_id": product_id,
                        "data": {
                            "standardization_status": "standardized",
                            "standardization_completed_at": datetime.utcnow()
                        }
                    })

                else:
                    # Не удалось стандартизировать
                    failed_count += 1
                    status_updates.append({
                        "_id": product_id,
                        "data": {
                            "standardization_status": "failed",
                            "standardization_error": "No standardization results"
                        }
                    })

            # 5. Сохраняем результаты
            if standardized_products:
                inserted = await self.standardized_store.bulk_insert_products(standardized_products)
                logger.info(f"Inserted {inserted} standardized products")

            # 6. Обновляем статусы в классифицированной БД
            if status_updates:
                await self.classified_store.bulk_update_status(status_updates)

            logger.info(
                f"Batch {batch_id} completed: "
                f"{standardized_count} standardized, {failed_count} failed"
            )

            return {
                "batch_id": batch_id,
                "total": len(classified_products),
                "standardized": standardized_count,
                "failed": failed_count
            }

        except Exception as e:
            logger.error(f"Error processing batch {batch_id}: {e}", exc_info=True)

            # Помечаем все товары как failed
            if 'classified_products' in locals():
                updates = [
                    {
                        "_id": str(p["_id"]),
                        "data": {
                            "standardization_status": "failed",
                            "standardization_error": str(e)
                        }
                    }
                    for p in classified_products
                ]
                await self.classified_store.bulk_update_status(updates)

            raise

    async def run_continuous_standardization(self):
        """Запустить непрерывную стандартизацию"""
        logger.info(f"Starting continuous standardization for worker {self.worker_id}")

        import asyncio
        import os

        # Проверяем настройку группировки
        enable_grouping = os.getenv("ENABLE_OKPD_GROUPING", "false").lower() == "true"

        if enable_grouping:
            logger.info("OKPD grouping enabled - processing products by OKPD2 groups for optimal caching")
            await self._run_with_okpd_grouping()
        else:
            await self._run_without_grouping()

    async def _run_with_okpd_grouping(self):
        """Запустить с группировкой по ОКПД2 для оптимального кэширования"""
        import asyncio

        while True:
            try:
                # Получаем статистику по группам
                stats = await self.classified_store.get_statistics()
                okpd_classes = stats.get("by_okpd_class", {})

                if not okpd_classes:
                    logger.info("No products to process, waiting...")
                    await asyncio.sleep(30)
                    continue

                # Обрабатываем по группам ОКПД2
                processed_any = False

                for okpd_prefix in sorted(okpd_classes.keys()):
                    # Проверяем есть ли товары для обработки в этой группе
                    count = await self.classified_store.collection.count_documents({
                        "status_stg2": "classified",
                        "okpd2_code": {"$regex": f"^{okpd_prefix}"},
                        "$or": [
                            {"standardization_status": {"$exists": False}},
                            {"standardization_status": "pending"}
                        ]
                    })

                    if count > 0:
                        logger.info(f"Processing OKPD2 group {okpd_prefix} ({count} products pending)")

                        # Обрабатываем все товары этой группы
                        while count > 0:
                            result = await self.process_batch(okpd_prefix=okpd_prefix)

                            if result["total"] == 0:
                                break

                            processed_any = True

                            # Обновляем счетчик
                            count = await self.classified_store.collection.count_documents({
                                "status_stg2": "classified",
                                "okpd2_code": {"$regex": f"^{okpd_prefix}"},
                                "$or": [
                                    {"standardization_status": {"$exists": False}},
                                    {"standardization_status": "pending"}
                                ]
                            })

                            # Задержка между батчами
                            delay = int(os.getenv("RATE_LIMIT_DELAY", "5"))
                            await asyncio.sleep(delay)

                if not processed_any:
                    logger.info("No more products to process, waiting...")
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in continuous standardization: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _run_without_grouping(self):
        """Запустить без группировки (старый метод)"""
        import asyncio
        import os

        while True:
            try:
                # Обрабатываем батч
                result = await self.process_batch()

                if result["total"] == 0:
                    # Нет товаров для обработки
                    logger.info("No products to process, waiting...")
                    await asyncio.sleep(30)
                else:
                    # Задержка между батчами
                    delay = int(os.getenv("RATE_LIMIT_DELAY", "5"))
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Error in continuous standardization: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def close(self):
        """Закрыть соединения"""
        await self.ai_standardizer.close()