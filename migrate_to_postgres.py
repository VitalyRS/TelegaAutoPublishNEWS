#!/usr/bin/env python3
"""
Скрипт миграции данных из SQLite в PostgreSQL

Использование:
    python migrate_to_postgres.py [path_to_sqlite_db]

Примечание: Перед запуском убедитесь, что:
1. PostgreSQL база данных создана и доступна
2. DATABASE_URL или DB_* параметры настроены в .env
3. requirements.txt установлены (включая psycopg2-binary)
"""

import sqlite3
import sys
import os
from datetime import datetime
from typing import List, Dict
import logging

# Добавляем путь для импорта модулей проекта
sys.path.insert(0, os.path.dirname(__file__))

from database import NewsDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SQLiteMigrator:
    """Класс для миграции данных из SQLite в PostgreSQL"""

    def __init__(self, sqlite_path: str):
        """
        Инициализация мигратора

        Args:
            sqlite_path: Путь к SQLite базе данных
        """
        self.sqlite_path = sqlite_path
        self.pg_db = None

    def read_sqlite_data(self) -> List[Dict]:
        """
        Читает все записи из SQLite базы

        Returns:
            Список записей из SQLite
        """
        if not os.path.exists(self.sqlite_path):
            raise FileNotFoundError(f"SQLite база не найдена: {self.sqlite_path}")

        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM news_queue')
            rows = cursor.fetchall()
            data = [dict(row) for row in rows]
            logger.info(f"Прочитано {len(data)} записей из SQLite")
            return data

        except Exception as e:
            logger.error(f"Ошибка чтения SQLite: {e}")
            raise
        finally:
            conn.close()

    def migrate_to_postgres(self, data: List[Dict]):
        """
        Мигрирует данные в PostgreSQL

        Args:
            data: Список записей для миграции
        """
        self.pg_db = NewsDatabase()
        logger.info("Подключение к PostgreSQL установлено")

        success_count = 0
        skip_count = 0
        error_count = 0

        for record in data:
            try:
                # Преобразуем is_urgent из INTEGER в BOOLEAN
                is_urgent = bool(record.get('is_urgent', 0))

                # Добавляем запись в PostgreSQL
                # Используем прямую вставку через connection для сохранения всех полей включая id
                with self.pg_db._get_connection() as conn:
                    cursor = conn.cursor()

                    # Преобразуем строковые timestamp в datetime если необходимо
                    scheduled_time = record.get('scheduled_time')
                    created_at = record.get('created_at')
                    published_at = record.get('published_at')

                    cursor.execute('''
                        INSERT INTO news_queue
                        (id, url, title, original_text, processed_text,
                         scheduled_time, status, is_urgent, created_at, published_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                    ''', (
                        record.get('id'),
                        record.get('url'),
                        record.get('title'),
                        record.get('original_text'),
                        record.get('processed_text'),
                        scheduled_time,
                        record.get('status', 'pending'),
                        is_urgent,
                        created_at,
                        published_at
                    ))

                    result = cursor.fetchone()
                    if result:
                        success_count += 1
                        logger.debug(f"Мигрирована запись ID={record.get('id')}")
                    else:
                        skip_count += 1
                        logger.debug(f"Пропущена дубликат записи URL={record.get('url')}")

            except Exception as e:
                error_count += 1
                logger.error(f"Ошибка миграции записи ID={record.get('id')}: {e}")

        logger.info(f"\nМиграция завершена:")
        logger.info(f"  Успешно: {success_count}")
        logger.info(f"  Пропущено (дубликаты): {skip_count}")
        logger.info(f"  Ошибки: {error_count}")

        # Обновляем sequence для автоинкремента
        if success_count > 0:
            try:
                with self.pg_db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT setval('news_queue_id_seq', (SELECT MAX(id) FROM news_queue))"
                    )
                    logger.info("Sequence автоинкремента обновлен")
            except Exception as e:
                logger.warning(f"Не удалось обновить sequence: {e}")

    def run(self):
        """Запускает процесс миграции"""
        try:
            logger.info(f"Начало миграции из {self.sqlite_path} в PostgreSQL")

            # Читаем данные из SQLite
            data = self.read_sqlite_data()

            if not data:
                logger.info("SQLite база пуста, миграция не требуется")
                return

            # Мигрируем в PostgreSQL
            self.migrate_to_postgres(data)

            logger.info("Миграция успешно завершена!")

        except Exception as e:
            logger.error(f"Критическая ошибка миграции: {e}")
            raise
        finally:
            if self.pg_db:
                self.pg_db.close()


def main():
    """Главная функция"""
    # Путь к SQLite базе по умолчанию
    sqlite_path = 'news_queue.db'

    # Если передан аргумент командной строки, используем его
    if len(sys.argv) > 1:
        sqlite_path = sys.argv[1]

    # Проверяем наличие переменных окружения для PostgreSQL
    if not os.getenv('DATABASE_URL') and not os.getenv('DB_HOST'):
        logger.error("Ошибка: не настроены переменные окружения для PostgreSQL")
        logger.error("Установите DATABASE_URL или DB_HOST/DB_USER/DB_PASSWORD/DB_NAME")
        sys.exit(1)

    # Запускаем миграцию
    migrator = SQLiteMigrator(sqlite_path)
    migrator.run()


if __name__ == '__main__':
    main()
