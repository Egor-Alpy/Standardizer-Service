#!/usr/bin/env python3
"""
Скрипт анализа результатов стандартизации
"""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.storage.classified_mongo import ClassifiedMongoStore
from src.storage.standardized_mongo import StandardizedMongoStore
from src.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


async def analyze_standardization():
    """Анализ результатов стандартизации"""
    classified_store = ClassifiedMongoStore(
        settings.classified_mongodb_database,
        settings.classified_collection_name
    )
    standardized_store = StandardizedMongoStore(
        settings.standardized_mongodb_database,
        settings.standardized_collection_name
    )

    try:
        # Проверяем подключения
        if not await classified_store.test_connection():
            console.print("[red]Failed to connect to classified MongoDB[/red]")
            return

        if not await standardized_store.test_connection():
            console.print("[red]Failed to connect to standardized MongoDB[/red]")
            return

        # Получаем статистику
        console.print("\n[bold cyan]Gathering statistics...[/bold cyan]\n")

        classified_stats = await classified_store.get_statistics()
        standardized_stats = await standardized_store.get_statistics()

        # Общая статистика
        total_classified = classified_stats.get("total_classified", 0)
        total_standardized = standardized_stats.get("total", 0)

        # Статистика по статусам
        by_status = classified_stats.get("by_status", {})
        pending = by_status.get("pending", 0) + by_status.get(None, total_classified - sum(by_status.values()))
        processing = by_status.get("processing", 0)
        standardized = by_status.get("standardized", 0)
        failed = by_status.get("failed", 0)

        # Процент стандартизации
        standardization_rate = (total_standardized / total_classified * 100) if total_classified > 0 else 0

        # Таблица общей статистики
        stats_table = Table(title="Общая статистика стандартизации", box=box.ROUNDED)
        stats_table.add_column("Показатель", style="cyan")
        stats_table.add_column("Значение", style="green", justify="right")
        stats_table.add_column("Процент", style="yellow", justify="right")

        stats_table.add_row("Всего классифицировано", f"{total_classified:,}", "100%")
        stats_table.add_row("Успешно стандартизовано", f"{total_standardized:,}", f"{standardization_rate:.1f}%")
        stats_table.add_row("Ожидают обработки", f"{pending:,}",
                            f"{pending / total_classified * 100:.1f}%" if total_classified > 0 else "0%")
        stats_table.add_row("В процессе", f"{processing:,}",
                            f"{processing / total_classified * 100:.1f}%" if total_classified > 0 else "0%")
        stats_table.add_row("С ошибками", f"{failed:,}",
                            f"{failed / total_classified * 100:.1f}%" if total_classified > 0 else "0%")

        console.print(stats_table)

        # Статистика по классам ОКПД2
        console.print("\n[bold cyan]Статистика по классам ОКПД2:[/bold cyan]\n")

        okpd_table = Table(title="Распределение по классам ОКПД2", box=box.ROUNDED)
        okpd_table.add_column("Класс", style="cyan")
        okpd_table.add_column("Классифицировано", style="green", justify="right")
        okpd_table.add_column("Стандартизовано", style="blue", justify="right")
        okpd_table.add_column("Процент", style="yellow", justify="right")

        classified_by_class = classified_stats.get("by_okpd_class", {})
        standardized_by_class = standardized_stats.get("by_okpd_class", {})

        for okpd_class in sorted(set(classified_by_class.keys()) | set(standardized_by_class.keys())):
            classified_count = classified_by_class.get(okpd_class, 0)
            standardized_count = standardized_by_class.get(okpd_class, 0)
            percentage = (standardized_count / classified_count * 100) if classified_count > 0 else 0

            okpd_table.add_row(
                okpd_class,
                f"{classified_count:,}",
                f"{standardized_count:,}",
                f"{percentage:.1f}%"
            )

        console.print(okpd_table)

        # Топ брендов
        if standardized_stats.get("top_brands"):
            console.print("\n[bold cyan]Топ-10 брендов:[/bold cyan]\n")

            brands_table = Table(title="Наиболее часто встречающиеся бренды", box=box.ROUNDED)
            brands_table.add_column("Бренд", style="cyan")
            brands_table.add_column("Количество товаров", style="green", justify="right")

            for brand, count in standardized_stats["top_brands"][:10]:
                brands_table.add_row(brand or "[без бренда]", f"{count:,}")

            console.print(brands_table)

        # Топ атрибутов
        if standardized_stats.get("top_attributes"):
            console.print("\n[bold cyan]Топ-20 стандартизированных атрибутов:[/bold cyan]\n")

            attrs_table = Table(title="Наиболее часто встречающиеся атрибуты", box=box.ROUNDED)
            attrs_table.add_column("Атрибут", style="cyan")
            attrs_table.add_column("Количество использований", style="green", justify="right")

            for attr_name, count in standardized_stats["top_attributes"]:
                attrs_table.add_row(attr_name, f"{count:,}")

            console.print(attrs_table)

        # Детальный анализ атрибутов
        console.print("\n[bold cyan]Анализ стандартизации атрибутов...[/bold cyan]\n")

        # Получаем примеры товаров для анализа
        sample_products = await standardized_store.find_products(limit=1000)

        # Анализируем эффективность стандартизации
        total_original_attrs = 0
        total_standardized_attrs = 0
        attr_coverage = defaultdict(int)

        for product in sample_products:
            original_attrs = len(product.get("original_attributes", []))
            standardized_attrs = len(product.get("standardized_attributes", []))

            total_original_attrs += original_attrs
            total_standardized_attrs += standardized_attrs

            # Считаем покрытие
            if original_attrs > 0:
                coverage = standardized_attrs / original_attrs
                if coverage == 0:
                    attr_coverage["0%"] += 1
                elif coverage < 0.25:
                    attr_coverage["<25%"] += 1
                elif coverage < 0.5:
                    attr_coverage["25-50%"] += 1
                elif coverage < 0.75:
                    attr_coverage["50-75%"] += 1
                elif coverage < 1.0:
                    attr_coverage["75-99%"] += 1
                else:
                    attr_coverage["100%"] += 1

        # Средний процент стандартизации атрибутов
        avg_attr_standardization = (
                    total_standardized_attrs / total_original_attrs * 100) if total_original_attrs > 0 else 0

        coverage_table = Table(title="Покрытие атрибутов стандартизацией", box=box.ROUNDED)
        coverage_table.add_column("Покрытие", style="cyan")
        coverage_table.add_column("Количество товаров", style="green", justify="right")
        coverage_table.add_column("Процент", style="yellow", justify="right")

        total_coverage_products = sum(attr_coverage.values())
        for coverage_level in ["0%", "<25%", "25-50%", "50-75%", "75-99%", "100%"]:
            count = attr_coverage.get(coverage_level, 0)
            percentage = (count / total_coverage_products * 100) if total_coverage_products > 0 else 0
            coverage_table.add_row(coverage_level, f"{count:,}", f"{percentage:.1f}%")

        console.print(coverage_table)

        # Итоговая панель
        summary = f"""
[bold green]Итоги анализа:[/bold green]

• Общий процент стандартизации: [bold yellow]{standardization_rate:.1f}%[/bold yellow]
• Средний процент стандартизации атрибутов: [bold yellow]{avg_attr_standardization:.1f}%[/bold yellow]
• Всего обработано товаров: [bold cyan]{total_standardized:,}[/bold cyan]
• Товаров с ошибками: [bold red]{failed:,}[/bold red]

[dim]Рекомендации:
- {'Процесс идет хорошо' if standardization_rate > 70 else 'Необходимо проверить качество стандартов'}
- {'Высокое покрытие атрибутов' if avg_attr_standardization > 60 else 'Рекомендуется расширить стандарты'}[/dim]
"""

        console.print(Panel(summary, title="Сводка", border_style="green"))

    except Exception as e:
        console.print(f"[red]Error during analysis: {e}[/red]")
        logger.error(f"Analysis error: {e}", exc_info=True)
    finally:
        await classified_store.close()
        await standardized_store.close()


async def main():
    await analyze_standardization()


if __name__ == "__main__":
    asyncio.run(main())