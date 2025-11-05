"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()


class Config:
    """Основные настройки бота"""

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    SOURCE_CHANNEL_ID = os.getenv('SOURCE_CHANNEL_ID')
    TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
    DEEPSEEK_API_URL = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')

    # Flask
    FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')

    # Настройки бота
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))
    MAX_ARTICLES_PER_RUN = int(os.getenv('MAX_ARTICLES_PER_RUN', 5))

    # Расписание публикаций (часы в формате 24ч)
    PUBLISH_SCHEDULE = os.getenv('PUBLISH_SCHEDULE', '8,12,16,20')

    # Ключевые слова для срочных новостей (публикуются немедленно)
    URGENT_KEYWORDS = os.getenv('URGENT_KEYWORDS', 'молния,breaking')

    # ID администратора для команд управления
    ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')

    # Стиль написания статей (informative, ironic, cynical, playful, mocking)
    ARTICLE_STYLE = os.getenv('ARTICLE_STYLE', 'informative')

    # Доступные стили
    AVAILABLE_STYLES = ['informative', 'ironic', 'cynical', 'playful', 'mocking']

    # PostgreSQL Database (Aiven or other)
    # Опция 1: Полный DATABASE_URL (рекомендуется для Aiven)
    DATABASE_URL = os.getenv('DATABASE_URL')

    # Опция 2: Отдельные параметры (если DATABASE_URL не указан)
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'news_queue')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_SSLMODE = os.getenv('DB_SSLMODE', 'require')  # Aiven требует SSL

    @classmethod
    def get_publish_hours(cls) -> list:
        """Получить часы публикации в виде списка"""
        return [int(h.strip()) for h in cls.PUBLISH_SCHEDULE.split(',')]

    @classmethod
    def get_urgent_keywords(cls) -> list:
        """Получить список ключевых слов для срочных новостей"""
        return [kw.strip().lower() for kw in cls.URGENT_KEYWORDS.split(',')]

    @classmethod
    def get_article_style(cls) -> str:
        """Получить текущий стиль написания статей"""
        style = cls.ARTICLE_STYLE.lower()
        return style if style in cls.AVAILABLE_STYLES else 'informative'

    @staticmethod
    def validate():
        """Проверка наличия обязательных настроек"""
        required = [
            'TELEGRAM_BOT_TOKEN',
            'SOURCE_CHANNEL_ID',
            'TARGET_CHANNEL_ID',
            'DEEPSEEK_API_KEY'
        ]

        missing = []
        for key in required:
            if not os.getenv(key):
                missing.append(key)

        # Проверка наличия настроек БД (или DATABASE_URL или отдельные параметры)
        database_url = os.getenv('DATABASE_URL')
        db_host = os.getenv('DB_HOST')

        if not database_url and not db_host:
            missing.append('DATABASE_URL или DB_HOST/DB_USER/DB_PASSWORD/DB_NAME')

        if missing:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")

        return True
