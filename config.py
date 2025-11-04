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

        if missing:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")

        return True
