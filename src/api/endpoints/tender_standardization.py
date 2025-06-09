from fastapi import APIRouter, Depends, HTTPException
import logging
from typing import List
import copy

from src.api.dependencies import verify_api_key
from src.services.ai_standardizer import AIStandardizer
from src.services.standards_matcher import StandardsMatcher
from src.models.tender import (
    TenderStandardizationRequest,
    TenderStandardizationResponse,
    TenderStatistics,
    TenderCharacteristic
)
from src.models.standardization import ProductForStandardization, ProductAttribute, StandardizedAttribute

router = APIRouter()
logger = logging.getLogger(__name__)


def convert_tender_characteristics_to_attributes(characteristics: List[TenderCharacteristic]) -> List[ProductAttribute]:
    """Конвертировать характеристики тендера в атрибуты для стандартизации"""
    attributes = []
    for char in characteristics:
        # Формируем значение с единицей измерения если есть
        value = char.value
        if char.unit:
            # Если единица измерения составная (через точку с запятой), берем первую
            unit = char.unit.split(';')[0].strip()
            # Не добавляем единицу к значению если она уже есть в значении
            if unit not in value:
                value = f"{char.value} {unit}"

        attr = ProductAttribute(
            attr_name=char.name,
            attr_value=value
        )
        attributes.append(attr)

    return attributes


def update_tender_characteristics(
        original_chars: List[TenderCharacteristic],
        standardized_attrs: List[StandardizedAttribute]
) -> List[TenderCharacteristic]:
    """Обновить характеристики тендера стандартизированными значениями"""
    # Создаем копию оригинальных характеристик
    updated_chars = copy.deepcopy(original_chars)

    # Создаем словарь стандартизированных атрибутов для быстрого поиска
    # Ключ - исходное название атрибута в нижнем регистре
    std_attrs_by_name = {}
    for attr in standardized_attrs:
        # Добавляем по стандартному имени
        std_attrs_by_name[attr.standard_name.lower()] = attr
        # Также добавляем по типу характеристики, если он отличается
        if attr.characteristic_type and attr.characteristic_type.lower() != attr.standard_name.lower():
            std_attrs_by_name[attr.characteristic_type.lower()] = attr

    # Обновляем характеристики
    for i, char in enumerate(updated_chars):
        char_name_lower = char.name.lower().strip()

        # Ищем соответствующий стандартизированный атрибут
        matched_attr = None

        # Прямое совпадение по имени
        if char_name_lower in std_attrs_by_name:
            matched_attr = std_attrs_by_name[char_name_lower]
        else:
            # Поиск по частичному совпадению
            for key, std_attr in std_attrs_by_name.items():
                if char_name_lower in key or key in char_name_lower:
                    matched_attr = std_attr
                    break

        if matched_attr:
            # Обновляем значения
            updated_chars[i].name = matched_attr.standard_name
            updated_chars[i].value = matched_attr.standard_value
            if matched_attr.unit:
                # Если у оригинальной характеристики была составная единица измерения,
                # сохраняем ее формат
                if char.unit and ';' in char.unit:
                    updated_chars[i].unit = char.unit  # Сохраняем оригинальный формат
                else:
                    updated_chars[i].unit = matched_attr.unit

    return updated_chars


@router.post("/tender/standardize", response_model=TenderStandardizationResponse)
async def standardize_tender(
        request: TenderStandardizationRequest,
        api_key: str = Depends(verify_api_key)
):
    """
    Стандартизировать характеристики товаров в тендере.
    Товары со строгим соответствием стандартам не обрабатываются.
    """
    logger.info(f"Starting tender standardization for tender {request.tender.tenderInfo.tenderNumber}")

    try:
        # Инициализируем сервисы
        ai_standardizer = AIStandardizer()
        standards_matcher = StandardsMatcher()

        # Копируем тендер для изменений
        result_tender = copy.deepcopy(request.tender)

        # Статистика
        total_items = len(request.tender.items)
        already_standardized = 0
        newly_standardized = 0
        failed = 0

        # Подготавливаем товары для стандартизации
        items_to_standardize = []
        item_indices = []  # Индексы товаров в исходном списке

        for idx, item in enumerate(request.tender.items):
            # Пропускаем товары без кода ОКПД2
            if not item.okpd2Code:
                logger.debug(f"Skipping item {item.id}: no OKPD2 code")
                continue

            # Пропускаем товары без характеристик
            if not item.characteristics:
                logger.debug(f"Skipping item {item.id}: no characteristics")
                already_standardized += 1  # Считаем их как уже стандартизированные
                continue

            # Проверяем строгое соответствие стандартам
            is_strict_match, reason = standards_matcher.check_strict_match(
                item.okpd2Code,
                item.characteristics
            )

            if is_strict_match:
                logger.info(f"Item {item.id} '{item.name}' strictly matches standards, skipping")
                already_standardized += 1
                continue

            logger.info(f"Item {item.id} '{item.name}' needs standardization: {reason}")

            # Конвертируем в модель для стандартизации
            attributes = convert_tender_characteristics_to_attributes(item.characteristics)

            product_for_std = ProductForStandardization(
                id=str(item.id),
                source_id=str(item.id),
                source_collection="tender",
                title=item.name,
                okpd2_code=item.okpd2Code,
                attributes=attributes
            )

            items_to_standardize.append(product_for_std)
            item_indices.append(idx)

        # Стандартизируем если есть что стандартизировать
        if items_to_standardize:
            logger.info(f"Sending {len(items_to_standardize)} items for standardization")

            # Отправляем на стандартизацию
            standardization_results = await ai_standardizer.standardize_batch(items_to_standardize)

            # Обновляем характеристики в результирующем тендере
            for product, idx in zip(items_to_standardize, item_indices):
                if product.id in standardization_results:
                    standardized_attrs = standardization_results[product.id]

                    # Обновляем характеристики товара
                    result_tender.items[idx].characteristics = update_tender_characteristics(
                        result_tender.items[idx].characteristics,
                        standardized_attrs
                    )

                    newly_standardized += 1
                else:
                    logger.warning(f"No standardization results for item {product.id}")
                    failed += 1

        # Формируем статистику
        statistics = TenderStatistics(
            total=total_items,
            already_standardized=already_standardized,
            newly_standardized=newly_standardized,
            failed=failed
        )

        logger.info(
            f"Tender standardization completed: "
            f"{already_standardized} already standardized, "
            f"{newly_standardized} newly standardized, "
            f"{failed} failed"
        )

        await ai_standardizer.close()

        return TenderStandardizationResponse(
            tender=result_tender,
            statistics=statistics
        )

    except Exception as e:
        logger.error(f"Error in tender standardization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))