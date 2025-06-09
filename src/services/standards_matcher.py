import json
import logging
from typing import Dict, List, Any, Tuple, Optional
from src.core.config import settings
from src.models.tender import TenderCharacteristic

logger = logging.getLogger(__name__)


class StandardsMatcher:
    """Сервис для проверки строгого соответствия стандартам"""

    def __init__(self):
        self.okpd2_standards = self._load_standards()

    def _load_standards(self) -> Dict[str, Any]:
        """Загрузить стандарты ОКПД2"""
        try:
            with open(settings.okpd2_characteristics_path, 'r', encoding='utf-8') as f:
                standards = json.load(f)
                return standards.get("okpd2_groups", {})
        except Exception as e:
            logger.error(f"Failed to load standards: {e}")
            return {}

    def _get_okpd_group(self, okpd2_code: str) -> str:
        """Получить группу ОКПД2 (первые 4 цифры с точкой)"""
        if not okpd2_code:
            return ""

        # Убираем точки если они есть в коде
        clean_code = okpd2_code.replace(".", "")

        # Преобразуем код в формат XX.XX
        if len(clean_code) >= 4:
            return f"{clean_code[:2]}.{clean_code[2:4]}"
        elif len(clean_code) == 2:
            # Для двузначных кодов ищем первую подходящую группу
            prefix = clean_code[:2]
            for key in sorted(self.okpd2_standards.keys()):
                if key.startswith(f"{prefix}."):
                    return key
            return ""
        else:
            return ""

    def check_strict_match(self, okpd2_code: str, characteristics: List[TenderCharacteristic]) -> Tuple[
        bool, Optional[str]]:
        """
        Проверить строгое соответствие характеристик стандартам ОКПД2

        Returns:
            (is_strict_match, reason)
        """
        # Получаем группу ОКПД2
        okpd_group = self._get_okpd_group(okpd2_code)
        if not okpd_group:
            return False, f"No OKPD2 group found for code {okpd2_code}"

        # Получаем стандарты для группы
        group_standards = self.okpd2_standards.get(okpd_group)
        if not group_standards:
            return False, f"No standards found for OKPD2 group {okpd_group}"

        # Создаем словарь характеристик из тендера для быстрого поиска
        tender_chars = {char.name.lower().strip(): char for char in characteristics}

        # Проверяем каждую характеристику из стандарта
        matched_count = 0
        total_standard_chars = len(group_standards)

        for char_key, char_standard in group_standards.items():
            char_name = char_standard.get("name", char_key)
            variations = char_standard.get("variations", [])
            standard_values = char_standard.get("values", [])
            standard_units = char_standard.get("units", [])

            # Ищем соответствующую характеристику в тендере
            found = False

            # Проверяем по основному названию
            if char_name.lower() in tender_chars:
                tender_char = tender_chars[char_name.lower()]
                found = True
            else:
                # Проверяем по вариациям
                for variation in variations:
                    if variation.lower() in tender_chars:
                        tender_char = tender_chars[variation.lower()]
                        found = True
                        break

            if not found:
                logger.debug(f"Standard characteristic '{char_name}' not found in tender")
                continue

            # Проверяем соответствие значения
            tender_value = tender_char.value.lower().strip()

            # Проверяем точное соответствие значениям
            value_matched = False
            if standard_values:
                for std_val in standard_values:
                    if std_val.lower() == tender_value:
                        value_matched = True
                        break

                    # Проверка числовых диапазонов
                    if any(op in tender_value for op in ['≥', '≤', '>', '<', '=']):
                        # Для количественных характеристик с операторами сравнения
                        # считаем совпадением если стандарт содержит похожие диапазоны
                        if any(op in std_val.lower() for op in ['≥', '≤', '>', '<', '=']):
                            value_matched = True
                            break

            # Проверяем единицы измерения
            unit_matched = True
            if standard_units and tender_char.unit:
                unit_matched = any(unit.lower() == tender_char.unit.lower() for unit in standard_units)

            if value_matched or (not standard_values and unit_matched):
                matched_count += 1
            else:
                logger.debug(
                    f"Value mismatch for '{char_name}': "
                    f"tender='{tender_value}', standard values={standard_values}"
                )

        # Проверяем, все ли характеристики из тендера есть в стандарте
        for tender_char in characteristics:
            found_in_standard = False
            char_name_lower = tender_char.name.lower().strip()

            for char_key, char_standard in group_standards.items():
                standard_name = char_standard.get("name", char_key).lower()
                variations = [v.lower() for v in char_standard.get("variations", [])]

                if char_name_lower == standard_name or char_name_lower in variations:
                    found_in_standard = True
                    break

            if not found_in_standard:
                return False, f"Tender characteristic '{tender_char.name}' not found in standards"

        # Строгое соответствие: все характеристики должны совпадать
        is_strict = matched_count == len(characteristics) == total_standard_chars

        if not is_strict:
            reason = (
                f"Partial match: {matched_count}/{len(characteristics)} tender chars matched, "
                f"{total_standard_chars} standard chars expected"
            )
            return False, reason

        return True, "All characteristics strictly match the standard"