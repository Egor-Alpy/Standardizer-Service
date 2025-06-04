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

        # Проверяем структуру - изменено на okpd2_groups
        if "okpd2_groups" not in data:
            console.print("[red]✗ Missing 'okpd2_groups' root key[/red]")
            return False

        okpd2_groups = data["okpd2_groups"]

        if not isinstance(okpd2_groups, dict):
            console.print("[red]✗ 'okpd2_groups' must be a dictionary[/red]")
            return False

        console.print("[green]✓ Basic structure is valid[/green]")

        # Статистика
        stats = {
            "total_groups": len(okpd2_groups),
            "total_characteristics": 0,
            "total_values": 0,
            "total_units": 0,
            "groups_with_errors": []
        }

        # Таблица групп
        groups_table = Table(title="ОКПД2 Groups", box=box.ROUNDED)
        groups_table.add_column("Code", style="cyan")
        groups_table.add_column("Characteristics", style="yellow", justify="right")
        groups_table.add_column("Total Values", style="green", justify="right")
        groups_table.add_column("Status", style="magenta")

        # Проверяем каждую группу
        for group_code, characteristics in okpd2_groups.items():
            errors = []
            group_values_count = 0

            # Проверяем формат кода группы (XX.XX)
            if not (len(group_code) == 5 and group_code[2] == '.' and
                    group_code[:2].isdigit() and group_code[3:5].isdigit()):
                errors.append(f"Invalid group code format: {group_code} (expected XX.XX)")

            # Проверяем что это словарь характеристик
            if not isinstance(characteristics, dict):
                errors.append("Group data must be a dictionary of characteristics")
                stats["groups_with_errors"].append(group_code)
                continue

            stats["total_characteristics"] += len(characteristics)

            # Проверяем каждую характеристику
            for char_name, char_data in characteristics.items():
                if not isinstance(char_data, dict):
                    errors.append(f"Characteristic '{char_name}' must be a dictionary")
                    continue

                # Проверяем наличие обязательных полей
                if "values" not in char_data:
                    errors.append(f"Characteristic '{char_name}' missing 'values' field")
                else:
                    if isinstance(char_data["values"], list):
                        stats["total_values"] += len(char_data["values"])
                        group_values_count += len(char_data["values"])
                    else:
                        errors.append(f"Characteristic '{char_name}' values must be a list")

                if "units" not in char_data:
                    errors.append(f"Characteristic '{char_name}' missing 'units' field")
                else:
                    if isinstance(char_data["units"], list):
                        stats["total_units"] += len(char_data["units"])
                    else:
                        errors.append(f"Characteristic '{char_name}' units must be a list")

            # Добавляем в таблицу
            status = "[green]✓ OK[/green]" if not errors else f"[red]✗ {len(errors)} errors[/red]"

            groups_table.add_row(
                group_code,
                str(len(characteristics)),
                str(group_values_count),
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

        # Проверяем на пустые значения
        console.print("\n[bold cyan]Checking for empty values and units...[/bold cyan]\n")

        empty_values_count = 0
        empty_units_count = 0

        for group_code, characteristics in okpd2_groups.items():
            for char_name, char_data in characteristics.items():
                if isinstance(char_data, dict):
                    if char_data.get("values") == []:
                        empty_values_count += 1
                        console.print(f"[yellow]Empty values in {group_code}.{char_name}[/yellow]")
                    if char_data.get("units") == []:
                        empty_units_count += 1
                        # Это нормально для многих характеристик

        if empty_values_count > 0:
            console.print(f"\n[yellow]Found {empty_values_count} characteristics with empty values[/yellow]")

        # Итоговая статистика
        console.print("\n[bold cyan]Summary:[/bold cyan]\n")

        summary_table = Table(box=box.ROUNDED)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green", justify="right")

        summary_table.add_row("Total OKPD2 groups", str(stats["total_groups"]))
        summary_table.add_row("Total characteristics", str(stats["total_characteristics"]))
        summary_table.add_row("Total values", str(stats["total_values"]))
        summary_table.add_row("Total units", str(stats["total_units"]))
        summary_table.add_row("Groups with errors", str(len(stats["groups_with_errors"])))
        summary_table.add_row("Average characteristics per group",
                              f"{stats['total_characteristics'] / stats['total_groups']:.1f}" if stats[
                                                                                                     'total_groups'] > 0 else "0")

        console.print(summary_table)

        # Рекомендации
        if stats["groups_with_errors"]:
            console.print("\n[yellow]⚠ Recommendations:[/yellow]")
            console.print("  • Fix errors in groups: " + ", ".join(stats["groups_with_errors"]))

        if empty_values_count > 0:
            console.print("  • Review characteristics with empty values")

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
    main()