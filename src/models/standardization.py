from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class StandardizationStatus(str, Enum):
    """Статусы стандартизации"""
    PENDING = "pending"
    PROCESSING = "processing"
    STANDARDIZED = "standardized"
    FAILED = "failed"


class ProductAttribute(BaseModel):
    """Атрибут товара"""
    attr_name: str
    attr_value: str


class StandardizedAttribute(BaseModel):
    """Стандартизированный атрибут"""
    original_name: str = Field(..., description="Исходное название атрибута")
    original_value: str = Field(..., description="Исходное значение")
    standard_name: str = Field(..., description="Стандартизированное название")
    standard_value: str = Field(..., description="Стандартизированное значение")
    characteristic_type: str = Field(..., description="Тип характеристики из стандарта")


class ProductForStandardization(BaseModel):
    """Товар для стандартизации"""
    id: str = Field(..., alias="_id")
    old_mongo_id: str
    collection_name: str
    title: str
    okpd2_code: str
    attributes: List[ProductAttribute]

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True

    @property
    def product_id(self) -> str:
        """Получить ID товара"""
        return self.id


class StandardizedProduct(BaseModel):
    """Стандартизированный товар"""
    # Идентификаторы
    old_mongo_id: str = Field(..., description="ID из исходной БД")
    classified_mongo_id: str = Field(..., description="ID из БД классификации")
    collection_name: str = Field(..., description="Исходная коллекция")

    # Основные данные товара
    title: str
    description: Optional[str] = None
    article: Optional[str] = None
    brand: Optional[str] = None
    country_of_origin: Optional[str] = None
    warranty_months: Optional[str] = None
    category: Optional[str] = None
    created_at: Optional[str] = None

    # Классификация
    okpd2_code: str
    okpd2_name: str
    okpd_group: List[str]

    # Атрибуты
    original_attributes: List[ProductAttribute] = Field(..., description="Исходные атрибуты")
    standardized_attributes: List[StandardizedAttribute] = Field(..., description="Стандартизированные атрибуты")

    # Поставщики
    suppliers: List[Dict[str, Any]] = Field(default_factory=list, description="Информация о поставщиках")

    # Метаданные стандартизации
    standardization_status: StandardizationStatus = Field(StandardizationStatus.PENDING)
    standardization_started_at: Optional[datetime] = None
    standardization_completed_at: Optional[datetime] = None
    standardization_batch_id: Optional[str] = None
    standardization_worker_id: Optional[str] = None
    standardization_error: Optional[str] = None

    class Config:
        use_enum_values = True


class StandardizationBatch(BaseModel):
    """Батч для стандартизации"""
    batch_id: str
    okpd2_code_prefix: str = Field(..., description="Префикс кода ОКПД2 (первые 2 цифры)")
    products: List[ProductForStandardization]
    total_products: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StandardizationStats(BaseModel):
    """Статистика стандартизации"""
    total_classified: int = Field(..., description="Всего классифицированных товаров")
    total_standardized: int = Field(..., description="Всего стандартизированных")
    pending: int = Field(..., description="Ожидают стандартизации")
    processing: int = Field(..., description="В процессе")
    failed: int = Field(..., description="С ошибками")
    standardization_percentage: float = Field(..., description="Процент стандартизации")
    by_okpd_class: Dict[str, Dict[str, int]] = Field(..., description="Статистика по классам ОКПД2")