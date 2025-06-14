from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    populate_by_name: bool = True

    # Source MongoDB (исходная БД с товарами)
    source_mongo_host: str = "localhost"
    source_mongo_port: int = 27017
    source_mongo_user: Optional[str] = None
    source_mongo_pass: Optional[str] = None
    source_mongo_authsource: Optional[str] = None
    source_mongo_authmechanism: str = "SCRAM-SHA-256"
    source_mongo_direct_connection: bool = False
    source_mongodb_database: str = "source_products"
    source_collection_name: str = "ipointer"  # Имя коллекции в исходной БД

    # Classified MongoDB (БД с классифицированными товарами)
    classified_mongo_host: str = "localhost"
    classified_mongo_port: int = 27017
    classified_mongo_user: Optional[str] = None
    classified_mongo_pass: Optional[str] = None
    classified_mongo_authsource: Optional[str] = None
    classified_mongo_authmechanism: str = "SCRAM-SHA-256"
    classified_mongo_direct_connection: bool = False
    classified_mongodb_database: str = "okpd_classifier"
    classified_collection_name: str = "products_classifier"  # Имя коллекции

    # Standardized MongoDB (новая БД для стандартизированных товаров)
    standardized_mongo_host: str = "localhost"
    standardized_mongo_port: int = 27017
    standardized_mongo_user: Optional[str] = None
    standardized_mongo_pass: Optional[str] = None
    standardized_mongo_authsource: Optional[str] = None
    standardized_mongo_authmechanism: str = "SCRAM-SHA-256"
    standardized_mongo_direct_connection: bool = False
    standardized_mongodb_database: str = "standardized_products"
    standardized_collection_name: str = "standardized_products"  # Имя коллекции

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None

    @property
    def redis_connection_string(self) -> str:
        if self.redis_password:
            redis_url = f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        else:
            redis_url = f"redis://:{self.redis_host}:{self.redis_port}"
        return redis_url

    # Anthropic
    anthropic_api_key: str
    # Используем Claude 3.7 Sonnet для максимальной эффективности с кэшированием
    anthropic_model: str = "claude-3-7-sonnet-20250105"

    # Prompt caching
    enable_prompt_caching: bool = True
    cache_ttl_type: str = "5m"  # или "1h" для часового кэша

    # Proxy settings for Anthropic API
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    socks_proxy: Optional[str] = None

    # Processing
    standardization_batch_size: int = 50  # Меньше батч для стандартизации
    max_workers: int = 1

    # Rate limit settings
    rate_limit_delay: int = 10
    max_retries: int = 3

    # API
    api_key: str

    # Paths
    okpd2_characteristics_path: str = "src/data/okpd2_characteristics.json"

    @property
    def source_mongodb_connection_string(self) -> str:
        """Формирование строки подключения для Source MongoDB"""
        if self.source_mongo_user and self.source_mongo_pass:
            connection_string = (
                f"mongodb://{self.source_mongo_user}:{quote_plus(self.source_mongo_pass)}@"
                f"{self.source_mongo_host}:{self.source_mongo_port}"
            )

            if self.source_mongo_authsource:
                connection_string += f"/{self.source_mongo_authsource}"
                connection_string += f"?authMechanism={self.source_mongo_authmechanism}"
            else:
                connection_string += f"/?authMechanism={self.source_mongo_authmechanism}"
        else:
            connection_string = f"mongodb://{self.source_mongo_host}:{self.source_mongo_port}"

        return connection_string

    @property
    def classified_mongodb_connection_string(self) -> str:
        """Формирование строки подключения для Classified MongoDB"""
        if self.classified_mongo_user and self.classified_mongo_pass:
            connection_string = (
                f"mongodb://{self.classified_mongo_user}:{quote_plus(self.classified_mongo_pass)}@"
                f"{self.classified_mongo_host}:{self.classified_mongo_port}"
            )

            if self.classified_mongo_authsource:
                connection_string += f"/{self.classified_mongo_authsource}"
                connection_string += f"?authMechanism={self.classified_mongo_authmechanism}"
            else:
                connection_string += f"/?authMechanism={self.classified_mongo_authmechanism}"
        else:
            connection_string = f"mongodb://{self.classified_mongo_host}:{self.classified_mongo_port}"

        return connection_string

    @property
    def standardized_mongodb_connection_string(self) -> str:
        """Формирование строки подключения для Standardized MongoDB"""
        if self.standardized_mongo_user and self.standardized_mongo_pass:
            connection_string = (
                f"mongodb://{self.standardized_mongo_user}:{quote_plus(self.standardized_mongo_pass)}@"
                f"{self.standardized_mongo_host}:{self.standardized_mongo_port}"
            )

            if self.standardized_mongo_authsource:
                connection_string += f"/{self.standardized_mongo_authsource}"
                connection_string += f"?authMechanism={self.standardized_mongo_authmechanism}"
            else:
                connection_string += f"/?authMechanism={self.standardized_mongo_authmechanism}"
        else:
            connection_string = f"mongodb://{self.standardized_mongo_host}:{self.standardized_mongo_port}"

        return connection_string

    @property
    def proxy_url(self) -> Optional[str]:
        """Получить URL прокси для Anthropic API"""
        if self.socks_proxy:
            return self.socks_proxy
        elif self.https_proxy:
            return self.https_proxy
        elif self.http_proxy:
            return self.http_proxy
        return None

    @property
    def cache_ttl_header(self) -> Optional[str]:
        """Получить заголовок для extended cache TTL"""
        if self.cache_ttl_type == "1h":
            return "extended-cache-ttl-2025-04-11"
        return None

    class Config:
        env_file = ".env"


settings = Settings()