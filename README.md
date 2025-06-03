# Сервис стандартизации характеристик товаров по ОКПД2

## 📋 Описание

Сервис автоматической стандартизации характеристик товаров согласно стандартам ОКПД2 с использованием Claude 3.7 Sonnet и prompt caching для оптимизации затрат.

### Основные возможности:
- ✅ Автоматическая стандартизация названий и значений атрибутов
- ✅ Поддержка prompt caching для снижения затрат до 90%
- ✅ Обработка товаров батчами по группам ОКПД2
- ✅ Сохранение полной информации о товаре
- ✅ API для мониторинга и управления
- ✅ Поддержка множественных воркеров

## 🚀 Быстрый старт

### 1. Подготовка окружения
```bash
# Клонировать репозиторий и установить зависимости
pip install -r requirements.txt

# Скопировать и настроить .env
cp .env.example .env
# Отредактировать .env - указать подключения к MongoDB и API ключи
```

### 2. Подготовка стандартов ОКПД2
Создайте файл `src/data/okpd2_characteristics.json` со стандартами характеристик.

Проверка файла:
```bash
make prepare-standards
```

### 3. Инициализация БД
```bash
make init-db
```

### 4. Запуск стандартизации
```bash
# В одном терминале - API
make dev-api

# В другом терминале - воркер
make worker-std API_KEY=your-api-key
```

## 📊 Архитектура

### Схема работы:
1. **Классифицированная БД** → Товары со статусом `status_stg2 = "classified"`
2. **Исходная БД** → Полные данные товара по `old_mongo_id`
3. **AI Стандартизатор** → Claude 3.7 Sonnet с prompt caching
4. **Стандартизированная БД** → Сохранение результатов

### Базы данных:
- **Исходная БД**: Оригинальные товары с атрибутами
- **Классифицированная БД**: Товары с кодами ОКПД2
- **Стандартизированная БД**: Товары со стандартизированными атрибутами

## 🔧 Настройка

### Переменные окружения (.env):
```bash
# Source MongoDB (исходная БД с товарами)
SOURCE_MONGO_HOST=localhost
SOURCE_MONGO_PORT=27017
SOURCE_MONGODB_DATABASE=source_products

# Classified MongoDB (БД с классифицированными товарами)
CLASSIFIED_MONGO_HOST=localhost
CLASSIFIED_MONGO_PORT=27017
CLASSIFIED_MONGODB_DATABASE=okpd_classifier

# Standardized MongoDB (новая БД для результатов)
STANDARDIZED_MONGO_HOST=localhost
STANDARDIZED_MONGO_PORT=27017
STANDARDIZED_MONGODB_DATABASE=standardized_products

# Anthropic API
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-7-sonnet-20250105

# Prompt caching
ENABLE_PROMPT_CACHING=true
CACHE_TTL_TYPE=5m  # или 1h для часового кэша

# Processing
STANDARDIZATION_BATCH_SIZE=50
RATE_LIMIT_DELAY=10
```

## 📈 Оптимизация с Prompt Caching

Сервис использует prompt caching, который позволяет снизить затраты до 90% и латентность до 85%:

- **Кэшируются**: Инструкции и стандарты ОКПД2 для каждой группы
- **Динамическая часть**: Только список товаров для стандартизации
- **TTL**: 5 минут (обновляется при использовании) или 1 час
- Cache read tokens не учитываются в ITPM лимите для Claude 3.7 Sonnet

### Экономия токенов:
- Без кэширования: ~50k токенов на батч
- С кэшированием: ~5k токенов на батч (90% экономия)

## 🚀 Оптимизация для Tier 2 аккаунтов

Если у вас Tier 2 аккаунт Anthropic с лимитами:
- 40,000 input tokens/min (excluding cache reads!)
- 16,000 output tokens/min

### Рекомендуемые настройки:
```bash
# .env
STANDARDIZATION_BATCH_SIZE=100  # Увеличенный батч
RATE_LIMIT_DELAY=5              # Минимальная задержка
MAX_WORKERS=3                   # 3 параллельных воркера
ENABLE_OKPD_GROUPING=true       # Группировка по ОКПД2
```

### Запуск 3 воркеров одновременно:
```bash
# Если установлен GNU parallel
make workers-all API_KEY=your-key

# Или вручную в разных терминалах
make worker-std   # Terminal 1
make worker-std-2 # Terminal 2
make worker-std-3 # Terminal 3
```

### Производительность с Tier 2:
- **200-300 товаров/минута** 
- **12,000-18,000 товаров/час**
- **10,000 товаров за 30-50 минут**
- **Стоимость**: ~$27 за 10,000 товаров

## 📊 Мониторинг

### Статистика в реальном времени:
```bash
make monitor API_KEY=your-key
```

### Мониторинг производительности со скоростью:
```bash
make monitor-perf
```

Показывает:
- Скорость обработки за минуту/5 минут/всего
- Оценка времени завершения
- Активные воркеры
- Прогресс в реальном времени

### Единоразовая статистика:
```bash
make stats API_KEY=your-key
```

### Пример вывода:
```json
{
  "total_classified": 15000,
  "total_standardized": 12000,
  "pending": 2500,
  "processing": 50,
  "standardized": 12000,
  "failed": 450,
  "standardization_percentage": 80.0,
  "by_okpd_class": {
    "17": 3500,
    "26": 2800,
    "10": 5700
  },
  "top_brands": [
    ["Мягкий знак", 1200],
    ["HP", 800]
  ],
  "top_attributes": [
    ["Вес", 8500],
    ["Цвет", 6200]
  ]
}
```

## 🛠 Управление процессом

### Сброс ошибок:
```bash
# Сбросить товары с ошибками для повторной обработки
make reset-failed API_KEY=your-key
```

### Очистка застрявших:
```bash
# Сбросить товары застрявшие в processing более 30 минут
make cleanup API_KEY=your-key
```

### Поиск по атрибутам:
```bash
# Найти товары по стандартизированному атрибуту
make search-attr ATTR=Вес VALUE="1 кг" API_KEY=your-key
```

## 📤 Экспорт данных

### Экспорт примеров:
```bash
make export API_KEY=your-key
```

### Сводка по атрибутам:
```bash
make attributes API_KEY=your-key
```

## 🐳 Docker

### Запуск в Docker:
```bash
# Сборка
docker-compose build

# Запуск
docker-compose up -d

# Масштабирование воркеров
docker-compose up -d --scale standardization-worker=3

# Логи
docker-compose logs -f standardization-worker
```

## 📝 Формат стандартов ОКПД2

Файл `src/data/okpd2_characteristics.json`:
```json
{
  "okpd2_characteristics": {
    "17": {
      "name": "Бумага и изделия из бумаги",
      "characteristics": {
        "layers": {
          "name": "Количество слоев",
          "variations": ["слой", "слоев", "слойность", "layers"],
          "values": ["1", "2", "3", "4", "многослойный"],
          "units": ["слой", "слоев"]
        },
        "color": {
          "name": "Цвет",
          "variations": ["цвет", "окраска", "цвет бумаги"],
          "values": ["белый", "серый", "цветной", "натуральный"]
        }
      }
    }
  }
}
```

## 🔍 API Endpoints

### Статистика:
```bash
GET /api/v1/standardization/stats
```

### Стандартизированные товары:
```bash
GET /api/v1/standardization/products/standardized?okpd_code=17&limit=100
```

### Конкретный товар:
```bash
GET /api/v1/standardization/products/{product_id}
```

### Управление:
```bash
POST /api/v1/standardization/reset-failed
POST /api/v1/standardization/cleanup-stuck
```

## ⚡ Производительность

- **Скорость обработки**: ~1000 товаров/час на воркер
- **Параллельность**: До 5 воркеров одновременно
- **Размер батча**: 50 товаров (оптимально для prompt caching)
- **Rate limiting**: Автоматическая обработка с retry

## 🚨 Решение проблем

### Товары не обрабатываются:
1. Проверить наличие классифицированных товаров:
   ```bash
   make db-check-classified
   ```
2. Проверить подключение к БД
3. Проверить API ключ Anthropic

### Высокие затраты на API:
1. Убедиться что `ENABLE_PROMPT_CACHING=true`
2. Проверить размер батча (не слишком маленький)
3. Использовать `CACHE_TTL_TYPE=1h` для редких запросов

### Ошибки стандартизации:
1. Проверить формат файла стандартов
2. Убедиться что есть стандарты для всех групп ОКПД2
3. Проверить логи воркера

## 📊 Ожидаемые результаты

- **Точность стандартизации**: ~85-90%
- **Экономия на API**: до 90% с prompt caching
- **Скорость**: 1000+ товаров/час

## 🔗 Связанные проекты

- [Сервис классификации ОКПД2](../classification_service/) - первый этап обработки товаров