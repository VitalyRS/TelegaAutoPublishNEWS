"""
Обработчик для работы с Telegram
"""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ParseMode
from config import Config
from database import NewsDatabase
from scheduler import PublicationScheduler

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Класс для работы с Telegram API"""

    def __init__(self):
        self.bot_token = Config.TELEGRAM_BOT_TOKEN
        self.source_channel = Config.SOURCE_CHANNEL_ID
        self.target_channel = Config.TARGET_CHANNEL_ID
        self.bot = Bot(token=self.bot_token)
        self.application = None
        self.db = NewsDatabase()
        self.scheduler = PublicationScheduler()
        self.urgent_keywords = Config.get_urgent_keywords()
        # Время запуска бота для фильтрации старых сообщений
        self.bot_start_time = datetime.now(timezone.utc)
        logger.info(f"Бот запущен. Будут обрабатываться только сообщения после {self.bot_start_time}")

    async def setup(self):
        """Инициализация приложения"""
        self.application = Application.builder().token(self.bot_token).build()

        # Обработчик сообщений из канала
        channel_handler = MessageHandler(
            filters.ChatType.CHANNEL & filters.TEXT,
            self.handle_channel_message
        )
        self.application.add_handler(channel_handler)

        # Команды управления ботом
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("queue", self.cmd_queue))
        self.application.add_handler(CommandHandler("publish_now", self.cmd_publish_now))
        self.application.add_handler(CommandHandler("clear_queue", self.cmd_clear_queue))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        logger.info("Telegram обработчик настроен")

    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка сообщений из канала

        Args:
            update: Обновление от Telegram
            context: Контекст бота
        """
        try:
            message = update.channel_post
            if not message or not message.text:
                return

            # Проверяем, что сообщение из нужного канала
            chat_id = str(message.chat.id)
            if chat_id != self.source_channel and f"@{message.chat.username}" != self.source_channel:
                return

            # Фильтруем старые сообщения - обрабатываем только новые с момента запуска бота
            if message.date < self.bot_start_time:
                logger.debug(f"Пропускаем старое сообщение от {message.date}")
                return

            logger.info(f"Получено новое сообщение из канала: {message.text[:100]}")

            # Извлекаем ссылки из сообщения
            urls = self.extract_urls(message.text)

            if urls:
                logger.info(f"Найдено {len(urls)} ссылок: {urls}")
                # Здесь будет вызов обработки статей
                context.job_queue.run_once(
                    self.process_urls,
                    when=1,
                    data={'urls': urls}
                )
            else:
                logger.info("В сообщении не найдено ссылок")

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения из канала: {e}")

    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """
        Извлечение URL из текста

        Args:
            text: Текст сообщения

        Returns:
            Список найденных URL
        """
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, text)
        return urls

    def is_urgent_news(self, text: str) -> bool:
        """
        Проверка, является ли новость срочной

        Args:
            text: Текст для проверки

        Returns:
            True если новость срочная
        """
        text_lower = text.lower()
        for keyword in self.urgent_keywords:
            if keyword in text_lower:
                logger.info(f"Обнаружено срочное ключевое слово: {keyword}")
                return True
        return False

    async def process_urls(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка найденных URL

        Args:
            context: Контекст бота
        """
        from news_parser import NewsParser
        from deepseek_client import DeepSeekClient

        urls = context.job.data.get('urls', [])
        parser = NewsParser()
        deepseek = DeepSeekClient()

        for url in urls[:Config.MAX_ARTICLES_PER_RUN]:
            try:
                # Парсинг статьи
                article_data = parser.parse_article(url)

                if not article_data or not parser.validate_article(article_data):
                    logger.warning(f"Статья не прошла валидацию: {url}")
                    continue

                # Проверка срочности
                is_urgent = self.is_urgent_news(article_data.get('title', '') + ' ' + article_data.get('text', ''))

                # Обработка через DeepSeek
                processed_text = deepseek.process_article(article_data)

                if processed_text:
                    # Определение времени публикации
                    scheduled_time = self.scheduler.get_next_available_slot(is_urgent=is_urgent)

                    # Добавление в очередь
                    news_id = self.db.add_news(
                        url=url,
                        title=article_data.get('title', ''),
                        original_text=article_data.get('text', ''),
                        processed_text=processed_text,
                        scheduled_time=scheduled_time,
                        is_urgent=is_urgent
                    )

                    if news_id:
                        if is_urgent:
                            # Срочные новости публикуем немедленно
                            logger.info(f"Срочная новость! Публикуем немедленно: {article_data.get('title')}")
                            await self.publish_news_by_id(news_id)
                        else:
                            logger.info(f"Новость добавлена в очередь. Публикация: {scheduled_time}")
                else:
                    logger.error(f"Не удалось обработать статью: {url}")

            except Exception as e:
                logger.error(f"Ошибка при обработке URL {url}: {e}")

    async def publish_news_by_id(self, news_id: int) -> bool:
        """
        Публикация новости по ID из базы данных

        Args:
            news_id: ID новости

        Returns:
            True если успешно
        """
        try:
            news = self.db.get_news_by_id(news_id)
            if not news:
                logger.error(f"Новость с ID {news_id} не найдена")
                return False

            # Формирование финального текста
            final_text = self._format_for_telegram_from_db(news)

            # Отправка в целевой канал
            await self.bot.send_message(
                chat_id=self.target_channel,
                text=final_text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )

            # Отметить как опубликованную
            self.db.mark_as_published(news_id)

            logger.info(f"Новость успешно опубликована: {news.get('title')}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при публикации новости {news_id}: {e}")
            self.db.mark_as_failed(news_id)
            return False

    async def publish_scheduled_news(self):
        """
        Публикация новостей по расписанию
        Вызывается APScheduler в нужное время
        """
        try:
            # Получаем новости готовые к публикации (по 1 на слот)
            news_list = self.db.get_news_for_publication(limit=1)

            for news in news_list:
                await self.publish_news_by_id(news['id'])

        except Exception as e:
            logger.error(f"Ошибка при публикации по расписанию: {e}")

    @staticmethod
    def _format_for_telegram_from_db(news: dict) -> str:
        """
        Форматирование текста для Telegram из БД

        Args:
            news: Данные новости из БД

        Returns:
            Отформатированный текст
        """
        processed_text = news.get('processed_text', '')
        url = news.get('url', '')

        footer = f"\n\n[Источник]({url})"

        # Telegram имеет лимит в 4096 символов
        max_length = 4096 - len(footer) - 100  # запас

        if len(processed_text) > max_length:
            processed_text = processed_text[:max_length] + "..."

        return processed_text + footer

    # Команды управления ботом

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        start_time_str = self.bot_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')
        await update.message.reply_text(
            "Бот автоматической публикации новостей запущен!\n\n"
            f"🕐 Время запуска: {start_time_str}\n"
            f"📡 Мониторинг канала: активен (только новые сообщения)\n\n"
            f"{self.scheduler.format_schedule()}\n\n"
            "Используйте /help для списка команд."
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
Доступные команды:

/start - Информация о боте
/status - Статус очереди новостей
/queue - Показать новости в очереди
/publish_now <id> - Опубликовать новость немедленно
/clear_queue - Очистить очередь новостей
/help - Это сообщение
"""
        await update.message.reply_text(help_text)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        try:
            stats = self.db.get_queue_status()

            status_text = f"""
📊 Статус очереди новостей:

Всего новостей: {stats.get('total', 0)}
⏳ В ожидании: {stats.get('pending', 0)}
✅ Опубликовано: {stats.get('published', 0)}
❌ Ошибки: {stats.get('failed', 0)}
🔥 Срочные: {stats.get('urgent', 0)}

{self.scheduler.format_schedule()}

Следующая публикация: {self.scheduler.get_next_publication_time().strftime('%Y-%m-%d %H:%M')}
"""

            if stats.get('next_news'):
                status_text += "\n\n📰 Следующие новости:\n"
                for news in stats['next_news']:
                    urgent_mark = "🔥 " if news['is_urgent'] else ""
                    status_text += f"{urgent_mark}{news['id']}. {news['title'][:50]}... ({news['scheduled_time']})\n"

            await update.message.reply_text(status_text)

        except Exception as e:
            logger.error(f"Ошибка в команде /status: {e}")
            await update.message.reply_text("Ошибка при получении статуса")

    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /queue"""
        try:
            news_list = self.db.get_pending_news()

            if not news_list:
                await update.message.reply_text("Очередь пуста")
                return

            queue_text = f"📋 Новости в очереди ({len(news_list)}):\n\n"

            for news in news_list[:20]:  # Показываем максимум 20
                urgent_mark = "🔥 " if news['is_urgent'] else ""
                queue_text += f"{urgent_mark}ID {news['id']}: {news['title'][:60]}...\n"
                queue_text += f"   ⏰ {news['scheduled_time']}\n"
                queue_text += f"   🔗 {news['url'][:50]}...\n\n"

            if len(news_list) > 20:
                queue_text += f"\n... и еще {len(news_list) - 20} новостей"

            await update.message.reply_text(queue_text)

        except Exception as e:
            logger.error(f"Ошибка в команде /queue: {e}")
            await update.message.reply_text("Ошибка при получении очереди")

    async def cmd_publish_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /publish_now <id>"""
        try:
            # Проверка прав администратора
            if Config.ADMIN_USER_ID and str(update.effective_user.id) != Config.ADMIN_USER_ID:
                await update.message.reply_text("У вас нет прав для выполнения этой команды")
                return

            if not context.args:
                await update.message.reply_text("Использование: /publish_now <id>")
                return

            news_id = int(context.args[0])

            await update.message.reply_text(f"Публикую новость ID {news_id}...")

            success = await self.publish_news_by_id(news_id)

            if success:
                await update.message.reply_text("✅ Новость успешно опубликована!")
            else:
                await update.message.reply_text("❌ Ошибка при публикации новости")

        except ValueError:
            await update.message.reply_text("Неверный формат ID")
        except Exception as e:
            logger.error(f"Ошибка в команде /publish_now: {e}")
            await update.message.reply_text("Ошибка при выполнении команды")

    async def cmd_clear_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /clear_queue"""
        try:
            # Проверка прав администратора
            if Config.ADMIN_USER_ID and str(update.effective_user.id) != Config.ADMIN_USER_ID:
                await update.message.reply_text("У вас нет прав для выполнения этой команды")
                return

            success = self.db.clear_queue()

            if success:
                await update.message.reply_text("✅ Очередь очищена")
            else:
                await update.message.reply_text("❌ Ошибка при очистке очереди")

        except Exception as e:
            logger.error(f"Ошибка в команде /clear_queue: {e}")
            await update.message.reply_text("Ошибка при выполнении команды")

    async def start(self):
        """Запуск бота"""
        await self.setup()
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Бот запущен и ожидает сообщений")

    async def stop(self):
        """Остановка бота"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        logger.info("Бот остановлен")
