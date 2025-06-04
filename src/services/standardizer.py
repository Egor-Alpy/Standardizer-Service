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
                    classified_product["collection_name"]
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
                    id=str(classified_product["_id"]),
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

        # ВРЕМЕННО отключаем группировку для отладки
        enable_grouping = False

        logger.info("Running without OKPD grouping for debugging")
        await self._run_without_grouping()

    async def _run_with_okpd_grouping(self):
        """Запустить с группировкой по ОКПД2 для оптимального кэширования"""
        import asyncio

        while True:
            try:
                # Получаем список всех уникальных ОКПД кодов
                pipeline = [
                    {"$match": {
                        "status_stg2": "classified",
                        "$or": [
                            {"standardization_status": {"$exists": False}},
                            {"standardization_status": "pending"}
                        ]
                    }},
                    {"$group": {
                        "_id": "$okpd2_code",
                        "count": {"$sum": 1}
                    }}
                ]

                cursor = self.classified_store.collection.aggregate(pipeline)
                okpd_codes = await cursor.to_list(length=None)

                if not okpd_codes:
                    logger.info("No products to process, waiting...")
                    await asyncio.sleep(30)
                    continue

                logger.info(f"Found {len(okpd_codes)} unique OKPD codes with pending products")

                # Группируем коды по первым 4 цифрам для сопоставления со словарем
                groups_to_process = {}
                for item in okpd_codes:
                    code = item["_id"]
                    if code and len(code) >= 4:
                        # Преобразуем в формат XX.XX
                        group_key = f"{code[:2]}.{code[2:4]}"

                        # Проверяем, есть ли эта группа в словаре стандартов
                        if group_key in self.ai_standardizer.okpd2_standards:
                            if group_key not in groups_to_process:
                                groups_to_process[group_key] = []
                            groups_to_process[group_key].append((code, item["count"]))
                        else:
                            logger.warning(f"No standards found for OKPD group {group_key} (code: {code})")

                if not groups_to_process:
                    logger.warning("No OKPD groups found in standards dictionary")
                    await asyncio.sleep(30)
                    continue

                logger.info(f"Will process {len(groups_to_process)} OKPD groups")

                # Обрабатываем каждую группу
                processed_any = False
                for group_key, codes_info in sorted(groups_to_process.items()):
                    total_in_group = sum(count for _, count in codes_info)
                    logger.info(
                        f"Processing OKPD2 group {group_key} ({total_in_group} products, {len(codes_info)} codes)")

                    # Обрабатываем все коды этой группы
                    for code, count in codes_info:
                        if count > 0:
                            logger.info(f"  Processing code {code} ({count} products)")

                            # Обрабатываем батчами
                            while True:
                                result = await self.process_batch(okpd_prefix=code)

                                if result["total"] == 0:
                                    break

                                processed_any = True

                                # Задержка между батчами
                                delay = int(os.getenv("RATE_LIMIT_DELAY", "5"))
                                await asyncio.sleep(delay)

                if not processed_any:
                    logger.info("No products were processed, waiting...")
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in continuous standardization: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _run_without_grouping(self):
        """Запустить без группировки (для отладки)"""
        import asyncio
        import os

        while True:
            try:
                # Проверяем количество товаров для обработки
                count = await self.classified_store.collection.count_documents({
                    "status_stg2": "classified",
                    "$or": [
                        {"standardization_status": {"$exists": False}},
                        {"standardization_status": "pending"}
                    ]
                })

                logger.info(f"Total products pending standardization: {count}")

                if count == 0:
                    logger.info("No products to process, waiting...")
                    await asyncio.sleep(30)
                    continue

                # Обрабатываем батч
                result = await self.process_batch()

                if result["total"] == 0:
                    # Возможно товары застряли в processing
                    processing_count = await self.classified_store.collection.count_documents({
                        "standardization_status": "processing"
                    })
                    logger.warning(f"No products fetched but {processing_count} are in processing status")

                    if processing_count > 0:
                        logger.info("Consider running cleanup-stuck command to reset stuck products")

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