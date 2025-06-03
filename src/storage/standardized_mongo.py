from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from src.core.config import settings
from src.models.standardization import StandardizedProduct

logger = logging.getLogger(__name__)


class StandardizedMongoStore:
    """Работа с MongoDB стандартизированных товаров"""

    def __init__(self, database_name: str, collection_name: str = "standardized_products"):
        self.client = AsyncIOMotorClient(
            settings.standardized_mongodb_connection_string,
            directConnection=settings.standardized_mongo_direct_connection,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
        self.db: AsyncIOMotorDatabase = self.client[database_name]
        self.collection = self.db[collection_name]

    async def initialize(self):
        """Инициализация хранилища и создание индексов"""
        connected = await self.test_connection()
        if not connected:
            raise Exception("Failed to connect to standardized MongoDB")

        await self._setup_indexes()

    async def _setup_indexes(self):
        """Создать необходимые индексы"""
        try:
            # Уникальный индекс по исходному ID
            await self.collection.create_index(
                [("old_mongo_id", 1), ("collection_name", 1)],
                unique=True
            )

            # Индексы для поиска
            await self.collection.create_index("okpd2_code")
            await self.collection.create_index("standardization_status")
            await self.collection.create_index("brand")
            await self.collection.create_index("category")
            await self.collection.create_index("standardization_completed_at")

            # Составной индекс для поиска по стандартизированным атрибутам
            await self.collection.create_index("standardized_attributes.standard_name")
            await self.collection.create_index("standardized_attributes.standard_value")

            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.warning(f"Error creating indexes (may already exist): {e}")

    async def insert_standardized_product(self, product: StandardizedProduct) -> bool:
        """Вставить стандартизированный товар"""
        try:
            document = product.dict()
            result = await self.collection.insert_one(document)
            logger.info(f"Inserted standardized product: {result.inserted_id}")
            return True
        except Exception as e:
            if "duplicate key error" in str(e):
                logger.warning(f"Product already exists: {product.old_mongo_id}")
                # Обновляем существующий документ
                result = await self.collection.replace_one(
                    {
                        "old_mongo_id": product.old_mongo_id,
                        "collection_name": product.collection_name
                    },
                    product.dict()
                )
                return result.modified_count > 0
            else:
                logger.error(f"Error inserting product: {e}")
                return False

    async def bulk_insert_products(self, products: List[StandardizedProduct]) -> int:
        """Массовая вставка стандартизированных товаров"""
        if not products:
            return 0

        from pymongo import ReplaceOne
        from pymongo.errors import BulkWriteError

        # Используем ReplaceOne для upsert
        bulk_operations = []
        for product in products:
            operation = ReplaceOne(
                {
                    "old_mongo_id": product.old_mongo_id,
                    "collection_name": product.collection_name
                },
                product.dict(),
                upsert=True
            )
            bulk_operations.append(operation)

        try:
            result = await self.collection.bulk_write(bulk_operations, ordered=False)
            inserted_count = result.upserted_count + result.modified_count
            logger.info(f"Bulk insert: {inserted_count} products processed")
            return inserted_count
        except BulkWriteError as e:
            # Обрабатываем частичный успех
            inserted_count = e.details.get('nUpserted', 0) + e.details.get('nModified', 0)
            logger.warning(f"Bulk insert completed with errors: {inserted_count} processed")
            return inserted_count

    async def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику стандартизации"""
        pipeline = [
            {"$facet": {
                "total": [{"$count": "count"}],
                "by_status": [
                    {"$group": {
                        "_id": "$standardization_status",
                        "count": {"$sum": 1}
                    }}
                ],
                "by_okpd_class": [
                    {"$group": {
                        "_id": {"$substr": ["$okpd2_code", 0, 2]},
                        "count": {"$sum": 1}
                    }}
                ],
                "by_brand": [
                    {"$group": {
                        "_id": "$brand",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 10}
                ],
                "attributes_stats": [
                    {"$unwind": "$standardized_attributes"},
                    {"$group": {
                        "_id": "$standardized_attributes.standard_name",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 20}
                ]
            }}
        ]

        cursor = self.collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            return {"total": 0}

        facets = result[0]
        stats = {
            "total": facets["total"][0]["count"] if facets["total"] else 0,
            "by_status": {s["_id"]: s["count"] for s in facets["by_status"] if s["_id"]},
            "by_okpd_class": {c["_id"]: c["count"] for c in facets["by_okpd_class"] if c["_id"]},
            "top_brands": [(b["_id"], b["count"]) for b in facets["by_brand"] if b["_id"]],
            "top_attributes": [(a["_id"], a["count"]) for a in facets["attributes_stats"]]
        }

        return stats

    async def find_products(
            self,
            filters: Dict[str, Any] = None,
            limit: int = 100,
            skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Поиск стандартизированных товаров"""
        query = filters or {}

        cursor = self.collection.find(query).skip(skip).limit(limit)
        products = await cursor.to_list(length=limit)

        # Преобразуем ObjectId в строки
        for product in products:
            product["_id"] = str(product["_id"])

        return products

    async def find_by_attributes(
            self,
            attribute_name: str,
            attribute_value: Optional[str] = None,
            limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Поиск по стандартизированным атрибутам"""
        query = {
            "standardized_attributes.standard_name": attribute_name
        }

        if attribute_value:
            query["standardized_attributes.standard_value"] = attribute_value

        return await self.find_products(query, limit)

    async def test_connection(self) -> bool:
        """Проверить подключение к БД"""
        try:
            await self.client.admin.command('ping')
            logger.info("Successfully connected to standardized MongoDB")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to standardized MongoDB: {e}")
            return False

    async def close(self):
        """Закрыть соединение"""
        self.client.close()