"""
Обработчик для работы с Telegram
"""
import logging
import re
import threading
from datetime import datetime, timezone
from typing import List, Optional
import telebot
from telebot import types
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
        self.bot = telebot.TeleBot(self.bot_token, parse_mode='Markdown')
        self.db = NewsDatabase()
        self.scheduler = PublicationScheduler()
        self.urgent_keywords = Config.get_urgent_keywords()
        # Время запуска бота для фильтрации старых сообщений
        self.bot_start_time = datetime.now(timezone.utc)
        logger.info(f"Бот запущен. Будут обрабатываться только сообщения после {self.bot_start_time}")

        # Настройка обработчиков
        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков сообщений и команд"""

        # Обработчик сообщений из каналов
        @self.bot.channel_post_handler(content_types=['text'])
        def handle_channel_post(message):
            self._handle_channel_message(message)

        # Команды управления ботом
        @self.bot.message_handler(commands=['start'])
        def cmd_start(message):
            self._cmd_start(message)

        @self.bot.message_handler(commands=['help'])
        def cmd_help(message):
            self._cmd_help(message)

        @self.bot.message_handler(commands=['status'])
        def cmd_status(message):
            self._cmd_status(message)

        @self.bot.message_handler(commands=['queue'])
        def cmd_queue(message):
            self._cmd_queue(message)

        @self.bot.message_handler(commands=['publish_now', 'publishnow'])
        def cmd_publish_now(message):
            self._cmd_publish_now(message)

        @self.bot.message_handler(commands=['clear_queue'])
        def cmd_clear_queue(message):
            self._cmd_clear_queue(message)

        logger.info("Обработчики Telegram настроены")

    def _handle_channel_message(self, message: types.Message):
        """
        Обработка сообщений из канала

        Args:
            message: Сообщение от Telegram
        """
        try:
            if not message or not message.text:
                return

            # Проверяем, что сообщение из нужного канала
            chat_id = str(message.chat.id)
            chat_username = f"@{message.chat.username}" if message.chat.username else None

            if chat_id != self.source_channel and chat_username != self.source_channel:
                return

            # Фильтруем старые сообщения - обрабатываем только новые с момента запуска бота
            message_date = datetime.fromtimestamp(message.date, tz=timezone.utc)
            if message_date < self.bot_start_time:
                logger.debug(f"Пропускаем старое сообщение от {message_date}")
                return

            logger.info(f"Получено новое сообщение из канала: {message.text[:100]}")

            # Извлекаем ссылки из сообщения
            urls = self.extract_urls(message.text)

            if urls:
                logger.info(f"Найдено {len(urls)} ссылок: {urls}")
                # Обработка URL в отдельном потоке чтобы не блокировать бота
                thread = threading.Thread(target=self._process_urls, args=(urls,))
                thread.start()
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

    def _process_urls(self, urls: List[str]):
        """
        Обработка найденных URL

        Args:
            urls: Список URL для обработки
        """
        from news_parser import NewsParser
        from deepseek_client import DeepSeekClient

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
                            self.publish_news_by_id(news_id)
                        else:
                            logger.info(f"Новость добавлена в очередь. Публикация: {scheduled_time}")
                else:
                    logger.error(f"Не удалось обработать статью: {url}")

            except Exception as e:
                logger.error(f"Ошибка при обработке URL {url}: {e}")

    def publish_news_by_id(self, news_id: int) -> bool:
        """
        Публикация новости по ID из базы данных

        Args:
            news_id: ID новости

        Returns:
            True если успешно
        """
        try:
            logger.info(f"Начинаем публикацию новости ID {news_id}")

            news = self.db.get_news_by_id(news_id)
            if not news:
                logger.error(f"Новость с ID {news_id} не найдена в базе данных")
                return False

            logger.info(f"Новость найдена: {news.get('title')[:50]}...")
            logger.info(f"Целевой канал: {self.target_channel}")

            # Формирование финального текста
            final_text = self._format_for_telegram_from_db(news)
            logger.info(f"Текст отформатирован, длина: {len(final_text)} символов")

            # Отправка в целевой канал
            logger.info(f"Отправляем сообщение в канал {self.target_channel}")
            self.bot.send_message(
                chat_id=self.target_channel,
                text=final_text,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            logger.info("Сообщение успешно отправлено")

            # Отметить как опубликованную
            self.db.mark_as_published(news_id)
            logger.info(f"Статус новости {news_id} обновлен на 'published'")

            logger.info(f"✅ Новость успешно опубликована: {news.get('title')}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при публикации новости {news_id}: {e}", exc_info=True)
            self.db.mark_as_failed(news_id)
            return False

    def publish_scheduled_news(self):
        """
        Публикация новостей по расписанию
        Вызывается APScheduler в нужное время
        """
        try:
            # Получаем новости готовые к публикации (по 1 на слот)
            news_list = self.db.get_news_for_publication(limit=1)

            for news in news_list:
                self.publish_news_by_id(news['id'])

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

    def _cmd_start(self, message: types.Message):
        """Команда /start"""
        start_time_str = self.bot_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')
        self.bot.reply_to(
            message,
            "Бот автоматической публикации новостей запущен!\n\n"
            f"🕐 Время запуска: {start_time_str}\n"
            f"📡 Мониторинг канала: активен (только новые сообщения)\n\n"
            f"{self.scheduler.format_schedule()}\n\n"
            "Используйте /help для списка команд."
        )

    def _cmd_help(self, message: types.Message):
        """Команда /help"""
        help_text = """
Доступные команды:

/start - Информация о боте
/status - Статус очереди новостей
/queue - Показать новости в очереди
/publishnow <id> (или /publish_now) - Опубликовать новость немедленно
/clear_queue - Очистить очередь новостей
/help - Это сообщение
"""
        self.bot.reply_to(message, help_text)

    def _cmd_status(self, message: types.Message):
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

            self.bot.reply_to(message, status_text)

        except Exception as e:
            logger.error(f"Ошибка в команде /status: {e}")
            self.bot.reply_to(message, "Ошибка при получении статуса")

    def _cmd_queue(self, message: types.Message):
        """Команда /queue"""
        try:
            news_list = self.db.get_pending_news()

            if not news_list:
                self.bot.reply_to(message, "Очередь пуста")
                return

            queue_text = f"📋 Новости в очереди ({len(news_list)}):\n\n"

            for news in news_list[:20]:  # Показываем максимум 20
                urgent_mark = "🔥 " if news['is_urgent'] else ""
                queue_text += f"{urgent_mark}ID {news['id']}: {news['title'][:60]}...\n"
                queue_text += f"   ⏰ {news['scheduled_time']}\n"
                queue_text += f"   🔗 {news['url'][:50]}...\n\n"

            if len(news_list) > 20:
                queue_text += f"\n... и еще {len(news_list) - 20} новостей"

            self.bot.reply_to(message, queue_text)

        except Exception as e:
            logger.error(f"Ошибка в команде /queue: {e}")
            self.bot.reply_to(message, "Ошибка при получении очереди")

    def _cmd_publish_now(self, message: types.Message):
        """Команда /publish_now <id> или /publishnow <id>"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /publishnow от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}. Требуется: {Config.ADMIN_USER_ID}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}\n"
                        f"Требуется ID администратора (установите в .env файле ADMIN_USER_ID)"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Извлекаем ID из команды
            parts = message.text.split()
            if len(parts) < 2:
                self.bot.reply_to(message, "Использование: /publishnow <id> или /publish_now <id>")
                return

            news_id = int(parts[1])
            logger.info(f"Попытка опубликовать новость ID: {news_id}")

            self.bot.reply_to(message, f"Публикую новость ID {news_id}...")

            success = self.publish_news_by_id(news_id)

            if success:
                self.bot.reply_to(message, "✅ Новость успешно опубликована!")
            else:
                self.bot.reply_to(message, "❌ Ошибка при публикации новости")

        except ValueError:
            self.bot.reply_to(message, "Неверный формат ID")
        except Exception as e:
            logger.error(f"Ошибка в команде /publish_now: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_clear_queue(self, message: types.Message):
        """Команда /clear_queue"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /clear_queue от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}. Требуется: {Config.ADMIN_USER_ID}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}\n"
                        f"Требуется ID администратора"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            success = self.db.clear_queue()

            if success:
                self.bot.reply_to(message, "✅ Очередь очищена")
            else:
                self.bot.reply_to(message, "❌ Ошибка при очистке очереди")

        except Exception as e:
            logger.error(f"Ошибка в команде /clear_queue: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def start_polling(self):
        """Запуск бота в режиме polling"""
        logger.info("Запуск бота в режиме polling")

        # Удаляем webhook если он был установлен ранее
        try:
            self.bot.remove_webhook()
            logger.info("Webhook удален, запускаем polling")
        except Exception as e:
            logger.warning(f"Не удалось удалить webhook: {e}")

        self.bot.infinity_polling(none_stop=True, interval=1)

    def stop(self):
        """Остановка бота"""
        logger.info("Остановка бота")
        self.bot.stop_polling()
