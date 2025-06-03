#!/usr/bin/env python3
"""
Скрипт мониторинга производительности стандартизации в реальном времени
"""
import asyncio
import time
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich import box

from src.storage.classified_mongo import ClassifiedMongoStore
from src.storage.standardized_mongo import StandardizedMongoStore
from src.core.config import settings

console = Console()


class PerformanceMonitor:
    def __init__(self):
        self.classified_store = None
        self.standardized_store = None
        self.start_time = time.time()
        self.last_counts = {}
        self.speeds = {
            "1min": 0,
            "5min": 0,
            "total": 0
        }
        self.history = []  # История для расчета скорости

    async def initialize(self):
        """Инициализация соединений"""
        self.classified_store = ClassifiedMongoStore(
            settings.classified_mongodb_database,
            settings.classified_collection_name
        )
        self.standardized_store = StandardizedMongoStore(
            settings.standardized_mongodb_database,
            settings.standardized_collection_name
        )

        if not await self.classified_store.test_connection():
            raise Exception("Cannot connect to classified MongoDB")
        if not await self.standardized_store.test_connection():
            raise Exception("Cannot connect to standardized MongoDB")

    async def get_current_stats(self):
        """Получить текущую статистику"""
        classified_stats = await self.classified_store.get_statistics()
        standardized_stats = await self.standardized_store.get_statistics()

        total_classified = classified_stats.get("total_classified", 0)
        total_standardized = standardized_stats.get("total", 0)

        by_status = classified_stats.get("by_status", {})
        pending = by_status.get("pending", 0) + by_status.get(None, total_classified - sum(by_status.values()))
        processing = by_status.get("processing", 0)
        failed = by_status.get("failed", 0)

        # Активные воркеры (товары в processing)
        active_workers = await self.classified_store.collection.distinct(
            "standardization_worker_id",
            {"standardization_status": "processing"}
        )

        return {
            "total_classified": total_classified,
            "total_standardized": total_standardized,
            "pending": pending,
            "processing": processing,
            "failed": failed,
            "active_workers": len(active_workers),
            "worker_ids": active_workers
        }

    def calculate_speeds(self, current_count):
        """Рассчитать скорость обработки"""
        now = time.time()

        # Добавляем в историю
        self.history.append({
            "time": now,
            "count": current_count
        })

        # Очищаем старые записи (старше 5 минут)
        cutoff_time = now - 300
        self.history = [h for h in self.history if h["time"] > cutoff_time]

        # Рассчитываем скорости
        speeds = {}

        # За последнюю минуту
        one_min_ago = now - 60
        one_min_records = [h for h in self.history if h["time"] > one_min_ago]
        if len(one_min_records) >= 2:
            time_diff = one_min_records[-1]["time"] - one_min_records[0]["time"]
            count_diff = one_min_records[-1]["count"] - one_min_records[0]["count"]
            speeds["1min"] = (count_diff / time_diff * 60) if time_diff > 0 else 0
        else:
            speeds["1min"] = 0

        # За последние 5 минут
        if len(self.history) >= 2:
            time_diff = self.history[-1]["time"] - self.history[0]["time"]
            count_diff = self.history[-1]["count"] - self.history[0]["count"]
            speeds["5min"] = (count_diff / time_diff * 60) if time_diff > 0 else 0
        else:
            speeds["5min"] = 0

        # Общая скорость
        total_time = now - self.start_time
        speeds["total"] = (current_count / total_time * 60) if total_time > 0 else 0

        return speeds

    def estimate_time_remaining(self, pending, speed):
        """Оценить оставшееся время"""
        if speed <= 0:
            return "∞"

        minutes = pending / speed
        if minutes < 60:
            return f"{int(minutes)} мин"
        elif minutes < 1440:
            hours = minutes / 60
            return f"{hours:.1f} ч"
        else:
            days = minutes / 1440
            return f"{days:.1f} д"

    def create_display(self, stats, speeds):
        """Создать отображение статистики"""
        layout = Layout()

        # Основная статистика
        stats_table = Table(title="📊 Статистика стандартизации", box=box.ROUNDED)
        stats_table.add_column("Показатель", style="cyan")
        stats_table.add_column("Значение", style="green", justify="right")
        stats_table.add_column("Процент", style="yellow", justify="right")

        total = stats["total_classified"]
        standardized = stats["total_standardized"]
        pending = stats["pending"]

        stats_table.add_row(
            "Всего классифицировано",
            f"{total:,}",
            "100%"
        )
        stats_table.add_row(
            "Стандартизовано",
            f"{standardized:,}",
            f"{standardized / total * 100:.1f}%" if total > 0 else "0%"
        )
        stats_table.add_row(
            "Ожидает обработки",
            f"{pending:,}",
            f"{pending / total * 100:.1f}%" if total > 0 else "0%"
        )
        stats_table.add_row(
            "В процессе",
            f"{stats['processing']:,}",
            f"{stats['processing'] / total * 100:.1f}%" if total > 0 else "0%"
        )
        stats_table.add_row(
            "С ошибками",
            f"{stats['failed']:,}",
            f"{stats['failed'] / total * 100:.1f}%" if total > 0 else "0%"
        )

        # Скорость обработки
        speed_table = Table(title="⚡ Скорость обработки", box=box.ROUNDED)
        speed_table.add_column("Период", style="cyan")
        speed_table.add_column("Товаров/мин", style="green", justify="right")
        speed_table.add_column("Товаров/час", style="yellow", justify="right")

        for period, label in [("1min", "Последняя минута"), ("5min", "Последние 5 минут"),
                              ("total", "С начала работы")]:
            speed = speeds[period]
            speed_table.add_row(
                label,
                f"{speed:.0f}",
                f"{speed * 60:,.0f}"
            )

        # Прогноз
        current_speed = speeds["1min"] if speeds["1min"] > 0 else speeds["5min"]
        eta = self.estimate_time_remaining(pending, current_speed)

        # Воркеры
        workers_info = f"Активных воркеров: {stats['active_workers']}"
        if stats['worker_ids']:
            workers_info += f"\nID: {', '.join(stats['worker_ids'][:5])}"
            if len(stats['worker_ids']) > 5:
                workers_info += f" и еще {len(stats['worker_ids']) - 5}"

        # Информационная панель
        info_text = f"""
[bold green]Время работы:[/bold green] {str(timedelta(seconds=int(time.time() - self.start_time)))}
[bold cyan]Осталось времени:[/bold cyan] {eta} (при текущей скорости)
[bold yellow]{workers_info}[/bold yellow]
[bold magenta]Время обновления:[/bold magenta] {datetime.now().strftime('%H:%M:%S')}
"""

        # Компонуем layout
        upper_layout = Layout()
        upper_layout.split_row(
            Layout(stats_table),
            Layout(speed_table)
        )

        layout.split_column(
            upper_layout,
            Layout(Panel(info_text.strip(), title="ℹ️ Информация", border_style="blue"), size=6)
        )

        return layout

    async def run(self):
        """Запустить мониторинг"""
        await self.initialize()

        # Получаем начальные данные
        initial_stats = await self.get_current_stats()
        self.start_count = initial_stats["total_standardized"]

        with Live(self.create_display(initial_stats, self.speeds), refresh_per_second=1) as live:
            while True:
                try:
                    # Получаем текущие данные
                    stats = await self.get_current_stats()

                    # Рассчитываем скорости
                    current_count = stats["total_standardized"] - self.start_count
                    speeds = self.calculate_speeds(current_count)
                    self.speeds = speeds

                    # Обновляем отображение
                    live.update(self.create_display(stats, speeds))

                    # Ждем 5 секунд
                    await asyncio.sleep(5)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    await asyncio.sleep(5)

    async def close(self):
        """Закрыть соединения"""
        if self.classified_store:
            await self.classified_store.close()
        if self.standardized_store:
            await self.standardized_store.close()


async def main():
    monitor = PerformanceMonitor()
    try:
        console.print("[bold cyan]Starting performance monitor...[/bold cyan]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")
        await monitor.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor stopped[/yellow]")
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())