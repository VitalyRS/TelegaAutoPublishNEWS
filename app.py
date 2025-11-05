"""
Основное приложение бота для автоматической публикации новостей
"""
import logging
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config import Config
from database import NewsDatabase
from telegram_handler import TelegramHandler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Flask приложение
app = Flask(__name__)

# База данных
database = None

# Telegram обработчик
telegram_handler = None

# Планировщик
scheduler = None


@app.route('/')
def index():
    """Главная страница"""
    return "Telegram News Bot is running!"


@app.route('/health')
def health():
    """Проверка здоровья"""
    return {"status": "ok"}, 200


@app.route(Config.WEBHOOK_PATH, methods=['POST'])
def webhook():
    """
    Обработка входящих обновлений от Telegram через webhook
    """
    from flask import request
    try:
        if request.headers.get('content-type') == 'application/json':
            json_data = request.get_json()

            if telegram_handler:
                telegram_handler.process_webhook_update(json_data)
                logger.debug("Webhook обновление успешно обработано")
                return {"status": "ok"}, 200
            else:
                logger.error("Telegram handler не инициализирован")
                return {"status": "error", "message": "Bot not initialized"}, 503
        else:
            logger.warning(f"Неверный content-type: {request.headers.get('content-type')}")
            return {"status": "error", "message": "Invalid content type"}, 400
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500


def publish_news_job():
    """
    Задача для публикации новостей по расписанию
    Вызывается APScheduler
    """
    try:
        if telegram_handler:
            telegram_handler.publish_scheduled_news()
    except Exception as e:
        logger.error(f"Ошибка в задаче публикации: {e}")


def cleanup_old_news_job():
    """
    Задача для очистки старых опубликованных статей
    Удаляет статьи старше 7 дней
    Вызывается APScheduler
    """
    try:
        if database:
            deleted_count = database.delete_old_published_news(days=7)
            logger.info(f"Автоматическая очистка БД: удалено {deleted_count} старых статей")
    except Exception as e:
        logger.error(f"Ошибка в задаче очистки БД: {e}")


def setup_scheduler():
    """Настройка планировщика публикаций и обслуживания"""
    global scheduler

    scheduler = BackgroundScheduler()

    # Получаем часы публикации из конфига
    publish_hours = Config.get_publish_hours()

    # Добавляем задачу для каждого часа публикации
    for hour in publish_hours:
        # Запускаем задачу в начале каждого часа (в первую минуту)
        trigger = CronTrigger(hour=hour, minute=0)
        scheduler.add_job(
            publish_news_job,
            trigger=trigger,
            id=f'publish_news_{hour}',
            name=f'Публикация новостей в {hour}:00',
            replace_existing=True
        )
        logger.info(f"Добавлена задача публикации на {hour}:00")

    # Добавляем задачу очистки старых статей (запуск каждый день в 3:00)
    cleanup_trigger = CronTrigger(hour=3, minute=0)
    scheduler.add_job(
        cleanup_old_news_job,
        trigger=cleanup_trigger,
        id='cleanup_old_news',
        name='Очистка старых опубликованных статей',
        replace_existing=True
    )
    logger.info("Добавлена задача очистки старых статей на 3:00 каждый день")

    scheduler.start()
    logger.info("Планировщик запущен")


def start_bot():
    """Запуск Telegram бота в режиме polling (блокирующий вызов)"""
    global telegram_handler, database

    try:
        # Валидация конфигурации
        Config.validate()

        # Инициализация базы данных
        database = NewsDatabase()
        logger.info("База данных инициализирована")

        # Загрузка настроек из БД (приоритет над .env)
        Config.init_from_database(database)
        logger.info("Настройки загружены из базы данных")
        logger.info(f"Текущие настройки: PUBLISH_SCHEDULE={Config.PUBLISH_SCHEDULE}, "
                   f"ARTICLE_STYLE={Config.ARTICLE_STYLE}, "
                   f"URGENT_KEYWORDS={Config.URGENT_KEYWORDS}")

        # Создание обработчика с передачей database
        telegram_handler = TelegramHandler(database=database)

        # Запуск бота в режиме polling (блокирующий вызов)
        logger.info("Telegram бот запущен в режиме polling")
        telegram_handler.start_polling()

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise


def start_bot_webhook():
    """Запуск Telegram бота в режиме webhook (не блокирующий)"""
    global telegram_handler, database

    try:
        # Валидация конфигурации
        Config.validate()

        # Инициализация базы данных
        database = NewsDatabase()
        logger.info("База данных инициализирована")

        # Загрузка настроек из БД (приоритет над .env)
        Config.init_from_database(database)
        logger.info("Настройки загружены из базы данных")
        logger.info(f"Текущие настройки: PUBLISH_SCHEDULE={Config.PUBLISH_SCHEDULE}, "
                   f"ARTICLE_STYLE={Config.ARTICLE_STYLE}, "
                   f"URGENT_KEYWORDS={Config.URGENT_KEYWORDS}")

        # Создание обработчика с передачей database
        telegram_handler = TelegramHandler(database=database)

        # Запуск бота в режиме webhook (не блокирующий)
        logger.info("Telegram бот запущен в режиме webhook")
        telegram_handler.start_webhook()

    except Exception as e:
        logger.error(f"Ошибка при запуске бота в режиме webhook: {e}")
        raise


def stop_bot():
    """Остановка Telegram бота"""
    global telegram_handler

    if telegram_handler:
        telegram_handler.stop()
        logger.info("Telegram бот остановлен")

    if scheduler:
        scheduler.shutdown()
        logger.info("Планировщик остановлен")


def run_bot():
    """Запуск бота в синхронном режиме"""
    try:
        # Настройка планировщика
        setup_scheduler()

        # Запуск бота (блокирующий вызов)
        start_bot()

    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Остановка бота
        stop_bot()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'webhook':
        # Запуск в режиме webhook с Flask
        logger.info("========================================")
        logger.info("Запуск бота в режиме WEBHOOK")
        logger.info(f"Webhook URL: {Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")
        logger.info(f"Flask будет слушать на {Config.FLASK_HOST}:{Config.FLASK_PORT}")
        logger.info("========================================")

        # Настройка планировщика
        setup_scheduler()

        # Инициализация бота в режиме webhook (не блокирующий)
        start_bot_webhook()

        # Запуск Flask сервера (блокирующий)
        app.run(
            host=Config.FLASK_HOST,
            port=Config.FLASK_PORT,
            debug=False
        )
    else:
        # Запуск в режиме polling (по умолчанию)
        logger.info("========================================")
        logger.info("Запуск бота в режиме POLLING")
        logger.info("========================================")
        run_bot()
