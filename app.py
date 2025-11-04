"""
Основное приложение бота для автоматической публикации новостей
"""
import asyncio
import logging
from flask import Flask
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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


async def publish_news_job():
    """
    Задача для публикации новостей по расписанию
    Вызывается APScheduler
    """
    try:
        if telegram_handler:
            await telegram_handler.publish_scheduled_news()
    except Exception as e:
        logger.error(f"Ошибка в задаче публикации: {e}")


def setup_scheduler():
    """Настройка планировщика публикаций"""
    global scheduler

    scheduler = AsyncIOScheduler()

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


async def start_bot():
    """Запуск Telegram бота"""
    global telegram_handler

    try:
        # Валидация конфигурации
        Config.validate()

        # Создание обработчика
        telegram_handler = TelegramHandler()

        # Запуск бота
        await telegram_handler.start()

        logger.info("Telegram бот успешно запущен")

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise


async def stop_bot():
    """Остановка Telegram бота"""
    global telegram_handler

    if telegram_handler:
        await telegram_handler.stop()
        logger.info("Telegram бот остановлен")

    if scheduler:
        scheduler.shutdown()
        logger.info("Планировщик остановлен")


def run_bot():
    """Запуск бота в асинхронном режиме"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Настройка планировщика
        setup_scheduler()

        # Запуск бота
        loop.run_until_complete(start_bot())

        # Держим бота запущенным
        loop.run_forever()

    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Остановка бота
        loop.run_until_complete(stop_bot())
        loop.close()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'flask':
        # Запуск в режиме Flask (для вебхуков)
        logger.info("Запуск в режиме Flask")
        setup_scheduler()

        # Запуск бота в отдельном потоке
        import threading
        bot_thread = threading.Thread(target=run_bot, daemon=True)
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
