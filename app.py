"""
Основное приложение бота для автоматической публикации новостей
"""
import logging
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config import Config
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


def setup_scheduler():
    """Настройка планировщика публикаций"""
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

    scheduler.start()
    logger.info("Планировщик запущен")


def start_bot():
    """Запуск Telegram бота"""
    global telegram_handler

    try:
        # Валидация конфигурации
        Config.validate()

        # Создание обработчика
        telegram_handler = TelegramHandler()

        # Запуск бота (блокирующий вызов)
        logger.info("Telegram бот запущен и ожидает сообщений")
        telegram_handler.start_polling()

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
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

    if len(sys.argv) > 1 and sys.argv[1] == 'flask':
        # Запуск в режиме Flask (для вебхуков)
        logger.info("Запуск в режиме Flask")
        setup_scheduler()

        # Запуск бота в отдельном потоке
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()

        # Запуск Flask
        app.run(
            host=Config.FLASK_HOST,
            port=Config.FLASK_PORT,
            debug=False
        )
    else:
        # Запуск в режиме polling (по умолчанию)
        logger.info("Запуск в режиме polling")
        run_bot()
