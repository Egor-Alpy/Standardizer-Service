from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import List, Dict, Any, Optional
from bson import ObjectId
import logging
from datetime import datetime

from src.core.config import settings
from src.models.standardization import ProductForStandardization, ProductAttribute

logger = logging.getLogger(__name__)


class ClassifiedMongoStore:
    """Работа с MongoDB классифицированных товаров"""

    def __init__(self, database_name: str, collection_name: str = "products_classifier"):
        self.client = AsyncIOMotorClient(
            settings.classified_mongodb_connection_string,
            directConnection=settings.classified_mongo_direct_connection,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
        self.db: AsyncIOMotorDatabase = self.client[database_name]
        self.collection = self.db[collection_name]

    async def get_products_for_standardization(
            self,
            limit: int = 50,
            okpd_prefix: Optional[str] = None
    ) -> List[ProductForStandardization]:
        """Получить товары готовые для стандартизации"""
        query = {
            "status_stg2": "classified",
            "okpd2_code": {"$exists": True, "$ne": None}
        }

        # Фильтр по префиксу ОКПД2 если указан
        if okpd_prefix:
            query["okpd2_code"] = {"$regex": f"^{okpd_prefix}"}

        # Атомарно получаем и блокируем товары
        products = []

        for _ in range(limit):
            doc = await self.collection.find_one_and_update(
                {
                    **query,
                    "$or": [
                        {"standardization_status": {"$exists": False}},
                        {"standardization_status": "pending"}
                    ]
                },
                {
                    "$set": {
                        "standardization_status": "processing",
                        "standardization_started_at": datetime.utcnow()
                    }
                },
                return_document=True
            )

            if doc:
                products.append(doc)
            else:
                break

        logger.info(f"Found {len(products)} products for standardization")
        return products

    async def update_standardization_status(
            self,
            product_id: str,
            status: str,
            error: Optional[str] = None
    ):
        """Обновить статус стандартизации"""
        update_data = {
            "standardization_status": status
        }

        if status == "failed" and error:
            update_data["standardization_error"] = error
        elif status == "standardized":
            update_data["standardization_completed_at"] = datetime.utcnow()

        await self.collection.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_data}
        )

    async def bulk_update_status(self, updates: List[Dict[str, Any]]):
        """Массовое обновление статусов"""
        from pymongo import UpdateOne

        bulk_operations = []
        for update in updates:
            operation = UpdateOne(
                {"_id": ObjectId(update["_id"])},
                {"$set": update["data"]}
            )
            bulk_operations.append(operation)

        if bulk_operations:
            result = await self.collection.bulk_write(bulk_operations)
            logger.info(f"Bulk update: {result.modified_count} products updated")

    async def get_statistics(self) -> Dict[str, int]:
        """Получить статистику по стандартизации"""
        pipeline = [
            {"$match": {"status_stg2": "classified"}},
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
                ]
            }}
        ]

        cursor = self.collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            return {"total": 0}

        facets = result[0]
        stats = {
            "total_classified": facets["total"][0]["count"] if facets["total"] else 0,
            "by_status": {s["_id"]: s["count"] for s in facets["by_status"] if s["_id"]},
            "by_okpd_class": {c["_id"]: c["count"] for c in facets["by_okpd_class"] if c["_id"]}
        }

        return stats

    async def test_connection(self) -> bool:
        """Проверить подключение к БД"""
        try:
            await self.client.admin.command('ping')
            logger.info("Successfully connected to classified MongoDB")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to classified MongoDB: {e}")
            return False

    async def close(self):
        """Закрыть соединение"""
        self.client.close()