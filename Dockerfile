FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Создание пользователя
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser src/ ./src/

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Порт
EXPOSE 8000

# Команда запуска по умолчанию
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
