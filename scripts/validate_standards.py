#!/usr/bin/env python3
"""
Скрипт валидации файла стандартов ОКПД2
"""
import json
import sys
from typing import Dict, List, Any, Set
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def validate_standards(file_path: str = "src/data/okpd2_characteristics.json") -> bool:
    """Валидация файла стандартов ОКПД2"""
    console.print(f"\n[bold cyan]Validating standards file: {file_path}[/bold cyan]\n")

    try:
        # Загружаем файл
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        console.print("[green]✓ File loaded successfully[/green]")

        # Проверяем структуру
        if "okpd2_characteristics" not in data:
            console.print("[red]✗ Missing 'okpd2_characteristics' root key[/red]")
            return False

        okpd2_chars = data["okpd2_characteristics"]

        if not isinstance(okpd2_chars, dict):
            console.print("[red]✗ 'okpd2_characteristics' must be a dictionary[/red]")
            return False

        console.print("[green]✓ Basic structure is valid[/green]")

        # Статистика
        stats = {
            "total_groups": len(okpd2_chars),
            "total_characteristics": 0,
            "total_variations": 0,
            "total_values": 0,
            "groups_with_errors": []
        }

        # Таблица групп
        groups_table = Table(title="ОКПД2 Groups", box=box.ROUNDED)
        groups_table.add_column("Code", style="cyan")
        groups_table.add_column("Name", style="green")
        groups_table.add_column("Characteristics", style="yellow", justify="right")
        groups_table.add_column("Status", style="magenta")

        # Проверяем каждую группу
        for group_code, group_data in okpd2_chars.items():
            errors = []

            # Проверяем формат кода группы
            if not group_code.isdigit() or len(group_code) != 2:
                errors.append(f"Invalid group code format: {group_code}")

            # Проверяем наличие обязательных полей
            if not isinstance(group_data, dict):
                errors.append("Group data must be a dictionary")
                stats["groups_with_errors"].append(group_code)
                continue

            if "name" not in group_data:
                errors.append("Missing 'name' field")

            if "characteristics" not in group_data:
                errors.append("Missing 'characteristics' field")
            else:
                chars = group_data["characteristics"]
                if not isinstance(chars, dict):
                    errors.append("'characteristics' must be a dictionary")
                else:
                    stats["total_characteristics"] += len(chars)

                    # Проверяем каждую характеристику
                    for char_key, char_data in chars.items():
                        if not isinstance(char_data, dict):
                            errors.append(f"Characteristic '{char_key}' must be a dictionary")
                            continue

                        # Обязательные поля характеристики
                        if "name" not in char_data:
                            errors.append(f"Characteristic '{char_key}' missing 'name' field")

                        if "variations" not in char_data:
                            errors.append(f"Characteristic '{char_key}' missing 'variations' field")
                        else:
                            if isinstance(char_data["variations"], list):
                                stats["total_variations"] += len(char_data["variations"])
                            else:
                                errors.append(f"Characteristic '{char_key}' variations must be a list")

                        # Опциональные поля
                        if "values" in char_data:
                            if isinstance(char_data["values"], list):
                                stats["total_values"] += len(char_data["values"])
                            else:
                                errors.append(f"Characteristic '{char_key}' values must be a list")

                        if "units" in char_data and not isinstance(char_data["units"], list):
                            errors.append(f"Characteristic '{char_key}' units must be a list")

            # Добавляем в таблицу
            status = "[green]✓ OK[/green]" if not errors else f"[red]✗ {len(errors)} errors[/red]"
            char_count = len(group_data.get("characteristics", {}))

            groups_table.add_row(
                group_code,
                group_data.get("name", "[Missing]"),
                str(char_count),
                status
            )

            if errors:
                stats["groups_with_errors"].append(group_code)
                for error in errors[:3]:  # Показываем первые 3 ошибки
                    console.print(f"  [red]→ {error}[/red]")
                if len(errors) > 3:
                    console.print(f"  [dim]... and {len(errors) - 3} more errors[/dim]")

        console.print("\n")
        console.print(groups_table)

        # Проверяем дубликаты вариаций между характеристиками
        console.print("\n[bold cyan]Checking for duplicate variations across characteristics...[/bold cyan]\n")

        all_variations = defaultdict(list)
        for group_code, group_data in okpd2_chars.items():
            if isinstance(group_data, dict) and "characteristics" in group_data:
                for char_key, char_data in group_data["characteristics"].items():
                    if isinstance(char_data, dict) and "variations" in char_data:
                        for variation in char_data.get("variations", []):
                            all_variations[variation.lower()].append(f"{group_code}.{char_key}")

        duplicates = {k: v for k, v in all_variations.items() if len(v) > 1}

        if duplicates:
            console.print(f"[yellow]Found {len(duplicates)} duplicate variations:[/yellow]")
            for variation, locations in list(duplicates.items())[:10]:
                console.print(f"  • '{variation}' found in: {', '.join(locations)}")
            if len(duplicates) > 10:
                console.print(f"  [dim]... and {len(duplicates) - 10} more duplicates[/dim]")
        else:
            console.print("[green]✓ No duplicate variations found[/green]")

        # Итоговая статистика
        console.print("\n[bold cyan]Summary:[/bold cyan]\n")

        summary_table = Table(box=box.ROUNDED)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green", justify="right")

        summary_table.add_row("Total OKPD2 groups", str(stats["total_groups"]))
        summary_table.add_row("Total characteristics", str(stats["total_characteristics"]))
        summary_table.add_row("Total variations", str(stats["total_variations"]))
        summary_table.add_row("Total predefined values", str(stats["total_values"]))
        summary_table.add_row("Groups with errors", str(len(stats["groups_with_errors"])))

        console.print(summary_table)

        # Рекомендации
        if stats["groups_with_errors"]:
            console.print("\n[yellow]⚠ Recommendations:[/yellow]")
            console.print("  • Fix errors in groups: " + ", ".join(stats["groups_with_errors"]))

        if stats["total_characteristics"] < stats["total_groups"] * 3:
            console.print("  • Consider adding more characteristics to groups")

        if duplicates:
            console.print("  • Review duplicate variations to ensure they are intentional")

        # Финальный статус
        is_valid = len(stats["groups_with_errors"]) == 0

        if is_valid:
            console.print("\n[bold green]✓ Standards file is valid![/bold green]")
        else:
            console.print(
                f"\n[bold red]✗ Standards file has errors in {len(stats['groups_with_errors'])} groups[/bold red]")

        return is_valid

    except FileNotFoundError:
        console.print(f"[red]✗ File not found: {file_path}[/red]")
        return False
    except json.JSONDecodeError as e:
        console.print(f"[red]✗ Invalid JSON: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate OKPD2 standards file')
    parser.add_argument('-f', '--file', default='src/data/okpd2_characteristics.json',
                        help='Path to standards file')

    args = parser.parse_args()

    is_valid = validate_standards(args.file)

    # Exit code для CI/CD
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    from collections import defaultdict

    main()
