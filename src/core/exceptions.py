class StandardizationException(Exception):
    """Базовое исключение для сервиса стандартизации"""
    pass


class AIStandardizerException(StandardizationException):
    """Исключение при работе с AI"""
    pass


class ProductFetchException(StandardizationException):
    """Исключение при получении данных товара"""
    pass


class DatabaseConnectionException(StandardizationException):
    """Исключение при подключении к БД"""
    pass


class StandardsLoadException(StandardizationException):
    """Исключение при загрузке стандартов"""
    pass