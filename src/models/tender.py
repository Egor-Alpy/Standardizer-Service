from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class TenderCharacteristic(BaseModel):
    """Характеристика товара в тендере"""
    id: int
    name: str
    value: str
    unit: Optional[str] = None
    type: str
    required: bool
    changeable: bool
    fillInstruction: str


class TenderItem(BaseModel):
    """Товар в тендере"""
    id: int
    name: str
    okpd2Code: str
    ktruCode: str
    quantity: float
    unitOfMeasurement: str
    unitPrice: Dict[str, Any]
    totalPrice: Dict[str, Any]
    characteristics: List[TenderCharacteristic]
    additionalRequirements: Optional[str] = None
    okpd2Name: Optional[str] = None


class TenderInfo(BaseModel):
    """Информация о тендере"""
    tenderName: str
    tenderNumber: str
    customerName: str
    description: Optional[str] = None
    purchaseType: str
    financingSource: str
    maxPrice: Dict[str, Any]
    deliveryInfo: Dict[str, Any]
    paymentInfo: Dict[str, Any]


class GeneralRequirements(BaseModel):
    """Общие требования тендера"""
    qualityRequirements: Optional[str] = None
    packagingRequirements: Optional[str] = None
    markingRequirements: Optional[str] = None
    warrantyRequirements: Optional[str] = None
    safetyRequirements: Optional[str] = None
    regulatoryRequirements: Optional[str] = None


class Tender(BaseModel):
    """Тендер"""
    tenderInfo: TenderInfo
    items: List[TenderItem]
    generalRequirements: GeneralRequirements
    attachments: List[Any] = Field(default_factory=list)


class TenderStatistics(BaseModel):
    """Статистика обработки тендера"""
    total: Optional[int] = None
    already_standardized: Optional[int] = None
    newly_standardized: Optional[int] = None
    failed: Optional[int] = None
    # Дополнительные поля для совместимости
    already_classified: Optional[int] = None
    newly_classified: Optional[int] = None


class TenderStandardizationRequest(BaseModel):
    """Запрос на стандартизацию тендера"""
    # tender: Tender
    statistics: Optional[TenderStatistics] = None


class TenderStandardizationResponse(BaseModel):
    """Ответ на стандартизацию тендера"""
    tender: Tender
    statistics: TenderStatistics