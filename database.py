"""
Модуль для работы с базой данных очереди новостей (PostgreSQL)
"""
import psycopg2
from psycopg2 import pool, errors
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager
import os

logger = logging.getLogger(__name__)


class NewsDatabase:
    """Класс для работы с PostgreSQL БД очереди новостей"""

    def __init__(self, database_url: Optional[str] = None):
        """
        Инициализация подключения к PostgreSQL

        Args:
            database_url: URL подключения к PostgreSQL (формат: postgresql://user:password@host:port/dbname)
                         Если не указан, используется DATABASE_URL из окружения или собирается из отдельных параметров
        """
        if database_url:
            self.database_url = database_url
        else:
            # Сначала пробуем получить полный DATABASE_URL из окружения (рекомендуется для Aiven)
            self.database_url = os.getenv('DATABASE_URL')

            # Если DATABASE_URL не задан, собираем из отдельных параметров
            if not self.database_url:
                db_host = os.getenv('DB_HOST', 'localhost')
                db_port = os.getenv('DB_PORT', '5432')
                db_name = os.getenv('DB_NAME', 'news_queue')
                db_user = os.getenv('DB_USER', 'postgres')
                db_password = os.getenv('DB_PASSWORD', '')
                db_sslmode = os.getenv('DB_SSLMODE', 'require')

                self.database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?sslmode={db_sslmode}"

        # Создаем connection pool для лучшей производительности
        try:
            self.connection_pool = pool.SimpleConnectionPool(
                1,  # минимум соединений
                10, # максимум соединений
                self.database_url
            )
            logger.info("Connection pool к PostgreSQL успешно создан")
        except Exception as e:
            logger.error(f"Ошибка создания connection pool: {e}")
            raise

        self._init_database()

    @contextmanager
    def _get_connection(self):
        """Контекстный менеджер для соединения с БД из pool"""
        conn = self.connection_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка работы с БД: {e}")
            raise
        finally:
            self.connection_pool.putconn(conn)

    def _init_database(self):
        """Инициализация структуры БД"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Создание таблицы с правильными типами PostgreSQL
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_queue (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT,
                    original_text TEXT,
                    processed_text TEXT,
                    scheduled_time TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    is_urgent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    published_at TIMESTAMP
                )
            ''')

            # Индексы для быстрого поиска
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_status
                ON news_queue(status)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_scheduled_time
                ON news_queue(scheduled_time)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_is_urgent
                ON news_queue(is_urgent)
            ''')

            # Композитный индекс для частого запроса
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_status_scheduled
                ON news_queue(status, scheduled_time)
            ''')

            logger.info("База данных PostgreSQL инициализирована")

    def add_news(self, url: str, title: str, original_text: str,
                 processed_text: str, scheduled_time: datetime,
                 is_urgent: bool = False) -> Optional[int]:
        """
        Добавить новость в очередь

        Args:
            url: URL новости
            title: Заголовок
            original_text: Исходный текст
            processed_text: Обработанный текст
            scheduled_time: Время публикации
            is_urgent: Срочная новость

        Returns:
            ID добавленной записи или None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO news_queue
                    (url, title, original_text, processed_text, scheduled_time, is_urgent)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (url, title, original_text, processed_text, scheduled_time, is_urgent))

                news_id = cursor.fetchone()[0]
                logger.info(f"Новость добавлена в очередь: ID={news_id}, URL={url}")
                return news_id

        except errors.UniqueViolation:
            logger.warning(f"Новость с URL {url} уже существует в очереди")
            return None
        except Exception as e:
            logger.error(f"Ошибка при добавлении новости: {e}")
            return None

    def get_news_for_publication(self, limit: int = 1) -> List[Dict]:
        """
        Получить новости готовые к публикации

        Args:
            limit: Количество новостей

        Returns:
            Список новостей
        """
        with self._get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT * FROM news_queue
                WHERE status = 'pending'
                AND scheduled_time <= %s
                ORDER BY is_urgent DESC, scheduled_time ASC
                LIMIT %s
            ''', (datetime.now(), limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_next_slot_news_count(self, slot_time: datetime) -> int:
        """
        Получить количество новостей в определенном временном слоте

        Args:
            slot_time: Время слота

        Returns:
            Количество новостей
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM news_queue
                WHERE status = 'pending'
                AND scheduled_time = %s
            ''', (slot_time,))

            result = cursor.fetchone()
            return result[0] if result else 0

    def mark_as_published(self, news_id: int) -> bool:
        """
        Отметить новость как опубликованную

        Args:
            news_id: ID новости

        Returns:
            True если успешно
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE news_queue
                    SET status = 'published', published_at = %s
                    WHERE id = %s
                ''', (datetime.now(), news_id))

                logger.info(f"Новость ID={news_id} отмечена как опубликованная")
                return True

        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса новости: {e}")
            return False

    def mark_as_failed(self, news_id: int) -> bool:
        """
        Отметить новость как неудачную

        Args:
            news_id: ID новости

        Returns:
            True если успешно
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE news_queue
                    SET status = 'failed'
                    WHERE id = %s
                ''', (news_id,))

                logger.info(f"Новость ID={news_id} отмечена как неудачная")
                return True

        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса новости: {e}")
            return False

    def get_queue_status(self) -> Dict:
        """
        Получить статус очереди

        Returns:
            Словарь со статистикой
        """
        with self._get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Общая статистика
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN is_urgent = TRUE THEN 1 ELSE 0 END) as urgent
                FROM news_queue
            ''')

            stats = dict(cursor.fetchone())

            # Следующие новости
            cursor.execute('''
                SELECT id, title, scheduled_time, is_urgent
                FROM news_queue
                WHERE status = 'pending'
                ORDER BY scheduled_time ASC
                LIMIT 5
            ''')

            next_news = [dict(row) for row in cursor.fetchall()]
            stats['next_news'] = next_news

            return stats

    def get_pending_news(self) -> List[Dict]:
        """
        Получить все новости в очереди

        Returns:
            Список новостей
        """
        with self._get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT id, title, url, scheduled_time, is_urgent
                FROM news_queue
                WHERE status = 'pending'
                ORDER BY scheduled_time ASC
            ''')

            return [dict(row) for row in cursor.fetchall()]

    def delete_news(self, news_id: int) -> bool:
        """
        Удалить новость из очереди

        Args:
            news_id: ID новости

        Returns:
            True если успешно
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM news_queue WHERE id = %s', (news_id,))
                logger.info(f"Новость ID={news_id} удалена из очереди")
                return True

        except Exception as e:
            logger.error(f"Ошибка при удалении новости: {e}")
            return False

    def clear_queue(self) -> bool:
        """
        Очистить всю очередь

        Returns:
            True если успешно
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM news_queue WHERE status = 'pending'")
                logger.info("Очередь новостей очищена")
                return True

        except Exception as e:
            logger.error(f"Ошибка при очистке очереди: {e}")
            return False

    def get_news_by_id(self, news_id: int) -> Optional[Dict]:
        """
        Получить новость по ID

        Args:
            news_id: ID новости

        Returns:
            Данные новости или None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM news_queue WHERE id = %s', (news_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def close(self):
        """Закрыть все соединения в pool"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("Connection pool закрыт")

    def __del__(self):
        """Деструктор для автоматического закрытия соединений"""
        try:
            self.close()
        except:
            pass
