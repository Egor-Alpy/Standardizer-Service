import asyncio
import logging
import sys
from typing import Optional

from src.services.standardizer import StandardizationService
from src.services.product_fetcher import ProductFetcher
from src.storage.classified_mongo import ClassifiedMongoStore
from src.storage.standardized_mongo import StandardizedMongoStore
from src.core.config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class StandardizationWorker:
    """Воркер для стандартизации товаров"""

    def __init__(self, worker_id: str = "std_worker_1"):
        self.worker_id = worker_id
        self.classified_store = None
        self.standardized_store = None
        self.product_fetcher = None
        self.standardization_service = None
        self.running = False
        logger.info(f"Initializing standardization worker: {self.worker_id}")

    async def start(self):
        """Запустить воркер"""
        logger.info(f"Starting standardization worker {self.worker_id}...")

        try:
            # Инициализируем хранилища
            logger.info("Connecting to classified MongoDB...")
            self.classified_store = ClassifiedMongoStore(
                settings.classified_mongodb_database,
                settings.classified_collection_name  # Используем из настроек
            )

            # Проверяем подключение
            if not await self.classified_store.test_connection():
                logger.error("Failed to connect to classified MongoDB!")
                return

            # Проверяем наличие классифицированных товаров
            stats = await self.classified_store.get_statistics()
            total_classified = stats.get("total_classified", 0)
            logger.info(f"Found {total_classified} classified products")

            if total_classified == 0:
                logger.warning("No classified products found!")
                logger.info("Please run classification service first.")
                return

            # Статистика по статусам стандартизации
            by_status = stats.get("by_status", {})
            pending = by_status.get("pending", 0) + by_status.get(None, total_classified - sum(by_status.values()))
            logger.info(f"Products pending standardization: {pending}")

            if pending == 0:
                logger.warning("No products pending standardization!")
                return

            logger.info("Connecting to standardized MongoDB...")
            self.standardized_store = StandardizedMongoStore(
                settings.standardized_mongodb_database,
                settings.standardized_collection_name  # Используем из настроек
            )

            # Инициализируем хранилище (создание индексов)
            await self.standardized_store.initialize()

            logger.info("Connecting to source MongoDB for product details...")
            self.product_fetcher = ProductFetcher()

            # Проверяем подключение к исходной БД
            if not await self.product_fetcher.test_connection():
                logger.error("Failed to connect to source MongoDB!")
                return

            logger.info("Creating standardization service...")
            logger.info(f"Using model: {settings.anthropic_model}")
            logger.info(f"Batch size: {settings.standardization_batch_size}")
            logger.info(f"Prompt caching: {'Enabled' if settings.enable_prompt_caching else 'Disabled'}")
            logger.info(f"Cache TTL: {settings.cache_ttl_type}")

            self.standardization_service = StandardizationService(
                classified_store=self.classified_store,
                standardized_store=self.standardized_store,
                product_fetcher=self.product_fetcher,
                batch_size=settings.standardization_batch_size,
                worker_id=self.worker_id
            )

            # Проверяем наличие файла стандартов
            import os
            if not os.path.exists(settings.okpd2_characteristics_path):
                logger.error(f"Standards file not found at {settings.okpd2_characteristics_path}")
                logger.error("Please create the standards file first!")
                return

            self.running = True
            logger.info(f"Worker {self.worker_id} initialized successfully. Starting continuous standardization...")

            # Показываем статистику по классам ОКПД2
            by_class = stats.get("by_okpd_class", {})
            if by_class:
                logger.info("Products by OKPD2 class:")
                for okpd_class, count in sorted(by_class.items()):
                    logger.info(f"  Class {okpd_class}: {count} products")

            # Запускаем непрерывную стандартизацию
            await self.standardization_service.run_continuous_standardization()

        except KeyboardInterrupt:
            logger.info(f"Worker {self.worker_id} interrupted by user")
            raise
        except Exception as e:
            logger.error(f"Standardization worker {self.worker_id} error: {e}", exc_info=True)
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Остановить воркер"""
        logger.info(f"Stopping standardization worker {self.worker_id}...")
        self.running = False

        if self.standardization_service:
            await self.standardization_service.close()

        if self.classified_store:
            await self.classified_store.close()

        if self.standardized_store:
            await self.standardized_store.close()

        if self.product_fetcher:
            await self.product_fetcher.close()

        logger.info(f"Worker {self.worker_id} stopped successfully")


async def main():
    """Запуск воркера из командной строки"""
    import argparse

    parser = argparse.ArgumentParser(description='Standardization worker')
    parser.add_argument('--worker-id', default='std_worker_1', help='Worker ID')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    args = parser.parse_args()

    # Настройка уровня логирования
    log_level = getattr(logging, args.log_level.upper())
    logging.getLogger().setLevel(log_level)
    logging.getLogger('src').setLevel(log_level)

    logger.info("=" * 60)
    logger.info("OKPD2 Product Standardization Worker Starting")
    logger.info("=" * 60)
    logger.info(f"Worker ID: {args.worker_id}")
    logger.info(f"Log Level: {args.log_level}")
    logger.info(f"Batch Size: {settings.standardization_batch_size}")
    logger.info(f"Rate Limit Delay: {settings.rate_limit_delay}s")
    logger.info(f"Max Retries: {settings.max_retries}")
    logger.info("=" * 60)

    try:
        worker = StandardizationWorker(args.worker_id)
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
