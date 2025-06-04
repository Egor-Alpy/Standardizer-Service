from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any

from src.api.dependencies import verify_api_key
from src.storage.classified_mongo import ClassifiedMongoStore
from src.storage.standardized_mongo import StandardizedMongoStore
from src.core.config import settings

router = APIRouter()


async def get_classified_store() -> ClassifiedMongoStore:
    """Получить экземпляр ClassifiedMongoStore"""
    return ClassifiedMongoStore(
        settings.classified_mongodb_database,
        settings.classified_collection_name
    )


async def get_standardized_store() -> StandardizedMongoStore:
    """Получить экземпляр StandardizedMongoStore"""
    return StandardizedMongoStore(
        settings.standardized_mongodb_database,
        settings.standardized_collection_name
    )


@router.get("/stats")
async def get_standardization_statistics(
        classified_store=Depends(get_classified_store),
        standardized_store=Depends(get_standardized_store),
        api_key: str = Depends(verify_api_key)
):
    """Получить общую статистику стандартизации"""
    # Статистика из классифицированной БД
    classified_stats = await classified_store.get_statistics()

    # Статистика из стандартизированной БД
    standardized_stats = await standardized_store.get_statistics()

    # Вычисляем процент стандартизации
    total_classified = classified_stats.get("total_classified", 0)
    total_standardized = standardized_stats.get("total", 0)

    standardization_percentage = 0
    if total_classified > 0:
        standardization_percentage = round(total_standardized / total_classified * 100, 2)

    # Статистика по статусам из классифицированной БД
    by_status = classified_stats.get("by_status", {})
    pending = by_status.get("pending", 0) + by_status.get(None, total_classified - sum(by_status.values()))
    processing = by_status.get("processing", 0)
    standardized = by_status.get("standardized", 0)
    failed = by_status.get("failed", 0)

    return {
        "total_classified": total_classified,
        "total_standardized": total_standardized,
        "pending": pending,
        "processing": processing,
        "standardized": standardized,
        "failed": failed,
        "standardization_percentage": standardization_percentage,
        "by_okpd_class": classified_stats.get("by_okpd_class", {}),
        "top_attributes": standardized_stats.get("top_attributes", [])
    }


@router.get("/products/standardized")
async def get_standardized_products(
        okpd_code: Optional[str] = Query(None, description="Filter by OKPD2 code"),
        attribute_name: Optional[str] = Query(None, description="Filter by attribute name"),
        attribute_value: Optional[str] = Query(None, description="Filter by attribute value"),
        limit: int = Query(100, ge=1, le=1000),
        skip: int = Query(0, ge=0),
        standardized_store=Depends(get_standardized_store),
        api_key: str = Depends(verify_api_key)
):
    """Получить стандартизированные товары с фильтрами"""
    if attribute_name:
        # Поиск по атрибутам
        products = await standardized_store.find_by_attributes(
            attribute_name=attribute_name,
            attribute_value=attribute_value,
            limit=limit
        )
    else:
        # Обычный поиск с фильтрами
        filters = {}
        if okpd_code:
            filters["okpd2_code"] = {"$regex": f"^{okpd_code}"}

        products = await standardized_store.find_products(
            filters=filters,
            limit=limit,
            skip=skip
        )

    return {
        "products": products,
        "count": len(products),
        "limit": limit,
        "skip": skip
    }


@router.get("/products/{product_id}")
async def get_standardized_product(
        product_id: str,
        standardized_store=Depends(get_standardized_store),
        api_key: str = Depends(verify_api_key)
):
    """Получить конкретный стандартизированный товар"""
    from bson import ObjectId

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=400, detail="Invalid product ID")

    products = await standardized_store.find_products(
        filters={"_id": ObjectId(product_id)},
        limit=1
    )

    if not products:
        raise HTTPException(status_code=404, detail="Product not found")

    return products[0]


@router.post("/reset-failed")
async def reset_failed_products(
        classified_store=Depends(get_classified_store),
        api_key: str = Depends(verify_api_key)
):
    """Сбросить статус failed товаров на pending для повторной стандартизации"""
    from pymongo import UpdateMany

    result = await classified_store.collection.update_many(
        {
            "status_stg2": "classified",
            "standardization_status": "failed"
        },
        {"$set": {"standardization_status": "pending"}}
    )

    return {
        "reset_count": result.modified_count,
        "message": f"Reset {result.modified_count} failed products to pending"
    }


@router.post("/cleanup-stuck")
async def cleanup_stuck_products(
        classified_store=Depends(get_classified_store),
        api_key: str = Depends(verify_api_key)
):
    """Сбросить застрявшие в processing товары"""
    from datetime import datetime, timedelta

    # Товары в processing более 30 минут считаем застрявшими
    stuck_threshold = datetime.utcnow() - timedelta(minutes=30)

    result = await classified_store.collection.update_many(
        {
            "standardization_status": "processing",
            "standardization_started_at": {"$lt": stuck_threshold}
        },
        {"$set": {"standardization_status": "pending"}}
    )

    return {
        "cleaned_count": result.modified_count,
        "message": f"Reset {result.modified_count} stuck products to pending"
    }


@router.get("/attributes/summary")
async def get_attributes_summary(
        okpd_class: Optional[str] = Query(None, description="Filter by OKPD2 class (2 digits)"),
        standardized_store=Depends(get_standardized_store),
        api_key: str = Depends(verify_api_key)
):
    """Получить сводку по стандартизированным атрибутам"""
    pipeline = [
        {"$unwind": "$standardized_attributes"},
        {"$group": {
            "_id": {
                "name": "$standardized_attributes.standard_name",
                "type": "$standardized_attributes.characteristic_type"
            },
            "count": {"$sum": 1},
            "unique_values": {"$addToSet": "$standardized_attributes.standard_value"}
        }},
        {"$project": {
            "attribute_name": "$_id.name",
            "characteristic_type": "$_id.type",
            "count": 1,
            "unique_values_count": {"$size": "$unique_values"},
            "sample_values": {"$slice": ["$unique_values", 10]}
        }},
        {"$sort": {"count": -1}}
    ]

    if okpd_class:
        pipeline.insert(0, {"$match": {"okpd2_code": {"$regex": f"^{okpd_class}"}}})

    cursor = standardized_store.collection.aggregate(pipeline)
    results = await cursor.to_list(length=None)

    return {
        "attributes": results,
        "total_attributes": len(results),
        "okpd_class_filter": okpd_class
    }


@router.get("/export/sample")
async def export_sample_data(
        okpd_code: Optional[str] = Query(None, description="Filter by OKPD2 code prefix"),
        limit: int = Query(10, ge=1, le=100),
        standardized_store=Depends(get_standardized_store),
        api_key: str = Depends(verify_api_key)
):
    """Экспортировать примеры стандартизированных товаров"""
    filters = {}
    if okpd_code:
        filters["okpd2_code"] = {"$regex": f"^{okpd_code}"}

    products = await standardized_store.find_products(
        filters=filters,
        limit=limit
    )

    # Форматируем для удобного просмотра
    export_data = []
    for product in products:
        export_item = {
            "old_mongo_id": product.get("old_mongo_id"),
            "classified_mongo_id": product.get("classified_mongo_id"),
            "collection_name": product.get("collection_name"),
            "okpd2_code": product.get("okpd2_code"),
            "okpd2_name": product.get("okpd2_name"),
            "standardized_attributes": [
                f"{attr['standard_name']}: {attr['standard_value']}"
                for attr in product.get("standardized_attributes", [])
            ]
        }
        export_data.append(export_item)

    return {
        "export_data": export_data,
        "count": len(export_data),
        "filters": {"okpd_code": okpd_code} if okpd_code else {}
    }