from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from src.models.standardization import StandardizedAttribute


class ProductAttribute(BaseModel):
    """Атрибут товара"""
    attr_name: str
    attr_value: str


class ClassifiedProductInput(BaseModel):
    """Классифицированный товар из сервиса классификации"""
    id: str
    title: str
    okpd_groups: List[str]
    okpd2_code: Optional[str]
    okpd2_name: Optional[str]
    attributes: List[ProductAttribute] = Field(default_factory=list)


class StandardizedProductResponse(BaseModel):
    """Стандартизированный товар для ответа"""
    id: str
    title: str
    okpd2_code: Optional[str]
    okpd2_name: Optional[str]
    okpd_groups: List[str]
    original_attributes: List[ProductAttribute]
    standardized_attributes: List[StandardizedAttribute]

    class Config:
        schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "title": "Ноутбук HP ProBook 450 G8",
                "okpd2_code": "26.20.11.110",
                "okpd2_name": "Компьютеры портативные массой не более 10 кг",
                "okpd_groups": ["26.20.1", "26.20.3"],
                "original_attributes": [
                    {"attr_name": "Процессор", "attr_value": "Intel Core i5"},
                    {"attr_name": "ОЗУ", "attr_value": "8 ГБ"}
                ],
                "standardized_attributes": [
                    {
                        "standard_name": "Процессор",
                        "standard_value": "Intel Core i5",
                        "unit": None,
                        "characteristic_type": "processor"
                    },
                    {
                        "standard_name": "Оперативная память",
                        "standard_value": "8",
                        "unit": "ГБ",
                        "characteristic_type": "ram"
                    }
                ]
            }
        }


class BatchStandardizationRequest(BaseModel):
    """Запрос на batch стандартизацию"""
    classified_products: List[ClassifiedProductInput] = Field(
        ...,
        description="Список классифицированных товаров из сервиса классификации"
    )

    class Config:
        schema_extra = {
            "example": {
                "classified_products": [
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "title": "Ноутбук HP ProBook 450 G8",
                        "okpd_groups": ["26.20.1", "26.20.3"],
                        "okpd2_code": "26.20.11.110",
                        "okpd2_name": "Компьютеры портативные массой не более 10 кг",
                        "attributes": [
                            {"attr_name": "Процессор", "attr_value": "Intel Core i5"},
                            {"attr_name": "ОЗУ", "attr_value": "8 ГБ"}
                        ]
                    }
                ]
            }
        }


class BatchStandardizationResponse(BaseModel):
    """Ответ batch стандартизации"""
    batch_id: str
    total_products: int
    standardized_products: List[StandardizedProductResponse]
    standardized_count: int
    failed_count: int

    class Config:
        schema_extra = {
            "example": {
                "batch_id": "std_batch_a1b2c3d4",
                "total_products": 1,
                "standardized_products": [...],  # См. StandardizedProductResponse
                "standardized_count": 1,
                "failed_count": 0
            }
        }
