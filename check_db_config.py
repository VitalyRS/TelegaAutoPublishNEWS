#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации в базе данных
"""
from database import NewsDatabase
from config import Config

# Валидация .env
Config.validate()

# Подключение к БД
db = NewsDatabase()

# Инициализация конфигурации из БД
Config.init_from_database(db)

print("\n=== Конфигурация из базы данных ===\n")

# Получаем все настройки
configs = {
    'PUBLISH_SCHEDULE': Config.PUBLISH_SCHEDULE,
    'URGENT_KEYWORDS': Config.URGENT_KEYWORDS,
    'ARTICLE_STYLE': Config.ARTICLE_STYLE,
    'TEXT_LENGTH': Config.TEXT_LENGTH,
    'MAX_ARTICLES_PER_RUN': Config.MAX_ARTICLES_PER_RUN,
    'CHECK_INTERVAL': Config.CHECK_INTERVAL,
}

for key, value in configs.items():
    print(f"{key}: {value}")

print(f"\nЧасы публикации (parsed): {Config.get_publish_hours()}")

# Проверяем статью ID 15
print("\n=== Информация о статье ID 15 ===\n")
news = db.get_news_by_id(15)
if news:
    print(f"Заголовок: {news['title']}")
    print(f"URL: {news['url']}")
    print(f"Запланирована на: {news['scheduled_time']}")
    print(f"Срочная: {news['is_urgent']}")
    print(f"Статус: {news['status']}")
else:
    print("Статья с ID 15 не найдена")

# Проверяем текущее время по Мадриду
from timezone_utils import now_madrid
print(f"\nТекущее время (Мадрид): {now_madrid()}")

db.close()
