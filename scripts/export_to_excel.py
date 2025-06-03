#!/usr/bin/env python3
"""
Скрипт экспорта стандартизированных товаров в Excel
"""
import asyncio
import pandas as pd
from datetime import datetime
import logging
import argparse
from typing import Optional, List, Dict, Any

from src.storage.standardized_mongo import StandardizedMongoStore
from src.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def export_to_excel(
        output_file: Optional[str] = None,
        okpd_filter: Optional[str] = None,
        limit: Optional[int] = None
):
    """Экспортировать стандартизированные товары в Excel"""
    store = StandardizedMongoStore(
        settings.standardized_mongodb_database,
        settings.standardized_collection_name
    )

    try:
        # Проверяем подключение
        if not await store.test_connection():
            logger.error("Failed to connect to standardized MongoDB")
            return

        # Формируем фильтры
        filters = {}
        if okpd_filter:
            filters["okpd2_code"] = {"$regex": f"^{okpd_filter}"}
            logger.info(f"Filtering by OKPD2 code: {okpd_filter}*")

        # Получаем товары
        logger.info("Fetching standardized products...")
        products = await store.find_products(filters, limit=limit or 10000)
        logger.info(f"Found {len(products)} products")

        if not products:
            logger.warning("No products found")
            return

        # Подготавливаем данные для экспорта
        export_data = []

        for product in products:
            # Базовая информация
            row = {
                "ID": product.get("old_mongo_id", ""),
                "Название": product.get("title", ""),
                "Артикул": product.get("article", ""),
                "Бренд": product.get("brand", ""),
                "Категория": product.get("category", ""),
                "Код ОКПД2": product.get("okpd2_code", ""),
                "Название ОКПД2": product.get("okpd2_name", ""),
                "Дата создания": product.get("created_at", ""),
                "Дата стандартизации": product.get("standardization_completed_at", "")
            }

            # Исходные атрибуты
            for i, attr in enumerate(product.get("original_attributes", [])[:10]):
                row[f"Исх_атрибут_{i + 1}_название"] = attr.get("attr_name", "")
                row[f"Исх_атрибут_{i + 1}_значение"] = attr.get("attr_value", "")

            # Стандартизированные атрибуты
            for i, attr in enumerate(product.get("standardized_attributes", [])[:10]):
                row[f"Станд_атрибут_{i + 1}_название"] = attr.get("standard_name", "")
                row[f"Станд_атрибут_{i + 1}_значение"] = attr.get("standard_value", "")
                row[f"Станд_атрибут_{i + 1}_тип"] = attr.get("characteristic_type", "")

            export_data.append(row)

        # Создаем DataFrame
        df = pd.DataFrame(export_data)

        # Генерируем имя файла если не указано
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"standardized_products_{timestamp}.xlsx"

        # Экспортируем в Excel с форматированием
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Стандартизированные товары', index=False)

            # Форматируем столбцы
            worksheet = writer.sheets['Стандартизированные товары']

            # Устанавливаем ширину столбцов
            column_widths = {
                'A': 20,  # ID
                'B': 50,  # Название
                'C': 15,  # Артикул
                'D': 20,  # Бренд
                'E': 30,  # Категория
                'F': 15,  # Код ОКПД2
                'G': 50,  # Название ОКПД2
            }

            for column, width in column_widths.items():
                worksheet.column_dimensions[column].width = width

            # Добавляем автофильтры
            worksheet.auto_filter.ref = worksheet.dimensions

        logger.info(f"Export completed: {output_file}")
        logger.info(f"Total products exported: {len(export_data)}")

        # Статистика
        stats = await store.get_statistics()
        logger.info("\nStatistics:")
        logger.info(f"  Total standardized: {stats.get('total', 0)}")
        logger.info(f"  By OKPD2 class: {stats.get('by_okpd_class', {})}")

    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
    finally:
        await store.close()


async def main():
    parser = argparse.ArgumentParser(description='Export standardized products to Excel')
    parser.add_argument('-o', '--output', help='Output Excel file path')
    parser.add_argument('-f', '--filter', help='Filter by OKPD2 code prefix')
    parser.add_argument('-l', '--limit', type=int, help='Limit number of products')

    args = parser.parse_args()

    await export_to_excel(
        output_file=args.output,
        okpd_filter=args.filter,
        limit=args.limit
    )


if __name__ == "__main__":
    asyncio.run(main())