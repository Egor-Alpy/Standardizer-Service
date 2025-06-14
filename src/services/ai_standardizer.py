import json
import logging
import os
import time
from typing import List, Dict, Any, Optional
from anthropic import AsyncAnthropic
import httpx

from src.core.config import settings
from src.models.standardization import (
    ProductForStandardization,
    StandardizedAttribute
)

logger = logging.getLogger(__name__)


class AIStandardizer:
    """AI стандартизатор с поддержкой prompt caching"""

    def __init__(self):
        self.api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model
        self.client = None
        self._http_client = None

        # Загружаем стандарты
        self.okpd2_standards = self._load_standards()

        # Кэши для каждой группы ОКПД2
        self.group_caches = {}
        self.last_cache_refresh = {}
        self.cache_refresh_interval = 240  # 4 минуты

        # Загружаем промпт шаблон
        self.prompt_template = self._load_prompt_template()

    def _load_standards(self) -> Dict[str, Any]:
        """Загрузить стандарты ОКПД2"""
        try:
            with open(settings.okpd2_characteristics_path, 'r', encoding='utf-8') as f:
                standards = json.load(f)
                logger.info(f"Loaded OKPD2 standards from {settings.okpd2_characteristics_path}")
                # Изменено: теперь ключ okpd2_groups вместо okpd2_characteristics
                return standards.get("okpd2_groups", {})
        except Exception as e:
            logger.error(f"Failed to load standards: {e}")
            return {}

    def _load_prompt_template(self) -> str:
        """Загрузить шаблон промпта"""
        try:
            with open("src/prompts/standardization_prompt.txt", 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load prompt template: {e}")
            return ""

    async def _ensure_client(self):
        """Создать клиент при необходимости"""
        if self.client is None:
            if settings.proxy_url:
                logger.info(f"Using proxy for Anthropic API: {settings.proxy_url}")
                self._http_client = httpx.AsyncClient(
                    proxy=settings.proxy_url,
                    timeout=httpx.Timeout(
                        timeout=300.0,
                        connect=30.0,
                        read=300.0,
                        write=30.0
                    )
                )
                self.client = AsyncAnthropic(
                    api_key=self.api_key,
                    http_client=self._http_client,
                    timeout=300.0
                )
            else:
                self.client = AsyncAnthropic(
                    api_key=self.api_key,
                    timeout=300.0
                )

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
                    logger.info(f"Using group {key} for short code {okpd2_code}")
                    return key
            # Если не нашли, возвращаем пустую строку
            logger.warning(f"No matching group found for code {okpd2_code}")
            return ""
        else:
            logger.warning(f"Invalid OKPD2 code format: {okpd2_code}")
            return ""

    def _prepare_cached_content(self, okpd_group: str) -> Optional[str]:
        """Подготовить кэшируемый контент для группы ОКПД2"""
        if okpd_group not in self.okpd2_standards:
            logger.warning(f"No standards found for OKPD group {okpd_group}")
            return None

        standards = self.okpd2_standards[okpd_group]
        standards_json = json.dumps(standards, ensure_ascii=False, indent=2)

        # Обновленный промпт для нового формата
        cached_content = f"""ЗАДАЧА: Стандартизировать характеристики товаров согласно предоставленным стандартам ОКПД2.

ИНСТРУКЦИИ:
1. Для каждого товара приведи атрибуты к стандартным названиям и значениям
2. Используй ТОЛЬКО характеристики из предоставленного стандарта для данной группы ОКПД2
3. Сопоставь исходные атрибуты с наиболее подходящими стандартными по смыслу
4. Если атрибут не соответствует ни одной стандартной характеристике - НЕ включай его в результат
5. Стандартизируй значения согласно допустимым вариантам из стандарта
6. Возвращай результат СТРОГО в формате JSON без дополнительного текста

ПРАВИЛА СТАНДАРТИЗАЦИИ:
- Название характеристики должно ТОЧНО соответствовать ключу из стандарта
- Значение должно быть из списка "values" или с правильными единицами измерения из "units"
- Если у характеристики есть единицы измерения - ОБЯЗАТЕЛЬНО укажи их в поле "unit"
- При сопоставлении учитывай смысл атрибута, а не только точное совпадение названия
- Приводи единицы измерения к стандартным из списка "units"
- Если значение не подходит под стандарт - выбери ближайшее подходящее или пропусти атрибут
- characteristic_type - это ключ характеристики из стандарта

ПРИМЕРЫ СОПОСТАВЛЕНИЯ:
- "количество слоев: 2" → standard_value: "2", unit: "слой"
- "вес 500г" → standard_value: "500", unit: "г"
- "цвет изделия" → "Цвет" (если есть в стандарте)
- "масса нетто" → "Вес" (если есть в стандарте)

ФОРМАТ ВЫВОДА (массив JSON):
[
  {{
    "product_id": "ID товара",
    "standardized_attributes": [
      {{
        "standard_name": "Название из ключа стандарта",
        "standard_value": "Стандартизированное значение",
        "unit": "Единица измерения из units или null",
        "characteristic_type": "Ключ характеристики из стандарта"
      }}
    ]
  }}
]

ДОСТУПНЫЕ СТАНДАРТЫ ДЛЯ ГРУППЫ {okpd_group}:
{standards_json}"""

        return cached_content

    async def _refresh_cache_if_needed(self, okpd_group: str):
        """Обновить кэш при необходимости"""
        current_time = time.time()
        last_refresh = self.last_cache_refresh.get(okpd_group, 0)

        if current_time - last_refresh > self.cache_refresh_interval:
            logger.info(f"Refreshing cache for OKPD group {okpd_group}")

            try:
                cached_content = self.group_caches.get(okpd_group)
                if cached_content:
                    # Отправляем минимальный запрос для обновления кэша
                    await self._send_request(
                        dynamic_content="Тестовый товар",
                        cached_content=cached_content,
                        max_tokens=10
                    )
                    self.last_cache_refresh[okpd_group] = current_time
                    logger.info(f"Cache for group {okpd_group} refreshed")
            except Exception as e:
                logger.warning(f"Failed to refresh cache: {e}")

    async def _send_request(
            self,
            dynamic_content: str,
            cached_content: str,
            max_tokens: int = 4000
    ) -> str:
        """Отправить запрос к API с кэшированием"""
        await self._ensure_client()

        try:
            # Формируем сообщение с кэшированием
            if settings.enable_prompt_caching and cached_content:
                messages = [{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": cached_content,
                            "cache_control": {
                                "type": "ephemeral",
                                "ttl": settings.cache_ttl_type
                            } if settings.cache_ttl_type == "1h" else {
                                "type": "ephemeral"
                            }
                        },
                        {
                            "type": "text",
                            "text": dynamic_content
                        }
                    ]
                }]

                # Заголовки для кэширования
                extra_headers = {"anthropic-beta": "prompt-caching-2024-07-31"}
                if settings.cache_ttl_header:
                    extra_headers["anthropic-beta"] += f",{settings.cache_ttl_header}"

                logger.debug("Sending request with prompt caching enabled")
            else:
                messages = [{"role": "user", "content": dynamic_content}]
                extra_headers = None

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
                temperature=0.0,
                extra_headers=extra_headers
            )

            # Логируем информацию о кэше
            if hasattr(response, 'usage'):
                usage = response.usage
                if hasattr(usage, 'cache_creation_input_tokens'):
                    logger.info(f"Cache creation tokens: {usage.cache_creation_input_tokens}")
                if hasattr(usage, 'cache_read_input_tokens'):
                    logger.info(f"Cache read tokens: {usage.cache_read_input_tokens}")
                logger.info(f"Total input tokens: {usage.input_tokens}, output: {usage.output_tokens}")

            return response.content[0].text

        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            raise

    async def standardize_batch(
            self,
            products: List[ProductForStandardization]
    ) -> Dict[str, List[StandardizedAttribute]]:
        """
        Стандартизировать батч товаров

        Returns:
            Dict с результатами для КАЖДОГО товара (даже если пустой массив)
        """
        if not products:
            return {}

        # Логируем коды для отладки
        logger.info(f"Standardizing batch of {len(products)} products")
        for p in products[:3]:  # Первые 3 для примера
            logger.info(f"  Product {p.product_id}: OKPD2 code = '{p.okpd2_code}'")

        # Группируем товары по группам ОКПД2 (первые 4 цифры)
        products_by_group = {}
        for product in products:
            logger.debug(f"Product {product.product_id} has OKPD2 code: '{product.okpd2_code}'")
            group = self._get_okpd_group(product.okpd2_code)

            if not group:
                # Если группа не найдена, добавляем в специальную группу
                if "UNMAPPED" not in products_by_group:
                    products_by_group["UNMAPPED"] = []
                products_by_group["UNMAPPED"].append(product)
            else:
                if group not in products_by_group:
                    products_by_group[group] = []
                products_by_group[group].append(product)

        all_results = {}

        # Обрабатываем каждую группу отдельно
        for okpd_group, group_products in products_by_group.items():
            if okpd_group == "UNMAPPED":
                logger.warning(f"Processing {len(group_products)} products with unmapped OKPD codes")
                # Возвращаем пустой результат для этих товаров (все атрибуты будут нестандартизированными)
                for product in group_products:
                    all_results[product.product_id] = []
                continue

            logger.info(f"Processing {len(group_products)} products for OKPD group '{okpd_group}'")

            # Получаем или создаем кэшированный контент
            if okpd_group not in self.group_caches:
                cached_content = self._prepare_cached_content(okpd_group)
                if not cached_content:
                    logger.error(f"Failed to prepare cache for group {okpd_group}")
                    # Возвращаем пустые результаты для всех товаров группы
                    for product in group_products:
                        all_results[product.product_id] = []
                    continue
                self.group_caches[okpd_group] = cached_content

            # Обновляем кэш при необходимости
            await self._refresh_cache_if_needed(okpd_group)

            # Формируем динамическую часть промпта
            products_data = []
            for product in group_products:
                product_info = {
                    "product_id": product.product_id,
                    "title": product.title,
                    "okpd2_code": product.okpd2_code,
                    "attributes": [
                        {
                            "name": attr.attr_name,
                            "value": attr.attr_value
                        } for attr in product.attributes
                    ]
                }
                products_data.append(product_info)

            dynamic_content = f"\nТОВАРЫ ДЛЯ СТАНДАРТИЗАЦИИ:\n{json.dumps(products_data, ensure_ascii=False, indent=2)}"

            try:
                # Отправляем запрос
                response = await self._send_request(
                    dynamic_content=dynamic_content,
                    cached_content=self.group_caches[okpd_group]
                )

                # Парсим результаты
                results = self._parse_response(response)

                # Убеждаемся, что у нас есть результат для каждого товара
                for product in group_products:
                    if product.product_id not in results:
                        # Если AI не вернул результат для товара, добавляем пустой массив
                        logger.warning(
                            f"No AI results for product {product.product_id}, will save with all unstandardized attributes")
                        results[product.product_id] = []

                all_results.update(results)

            except Exception as e:
                logger.error(f"Error processing group {okpd_group}: {e}")
                # При ошибке все товары группы получают пустые результаты
                for product in group_products:
                    all_results[product.product_id] = []
                continue

        return all_results

    def _parse_response(self, response: str) -> Dict[str, List[StandardizedAttribute]]:
        """Парсинг ответа от AI"""
        results = {}

        try:
            # Извлекаем JSON из ответа
            json_start = response.find('[')
            json_end = response.rfind(']') + 1

            if json_start == -1 or json_end == 0:
                logger.error("No JSON array found in response")
                return results

            json_str = response[json_start:json_end]
            parsed_data = json.loads(json_str)

            # Преобразуем в модели
            for product_data in parsed_data:
                product_id = product_data.get("product_id")
                if not product_id:
                    continue

                standardized_attrs = []
                for attr in product_data.get("standardized_attributes", []):
                    try:
                        standardized_attr = StandardizedAttribute(
                            standard_name=attr.get("standard_name", ""),
                            standard_value=attr.get("standard_value", ""),
                            unit=attr.get("unit"),  # Может быть None
                            characteristic_type=attr.get("characteristic_type", "")
                        )
                        standardized_attrs.append(standardized_attr)
                    except Exception as e:
                        logger.warning(f"Error parsing attribute: {e}")
                        continue

                results[product_id] = standardized_attrs

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response: {response}")
        except Exception as e:
            logger.error(f"Error parsing response: {e}")

        return results

    async def close(self):
        """Закрыть соединения"""
        if self.client:
            await self.client.close()
        if self._http_client:
            await self._http_client.aclose()