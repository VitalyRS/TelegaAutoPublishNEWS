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

    def __init__(self, database: Optional[NewsDatabase] = None):
        self.bot_token = Config.TELEGRAM_BOT_TOKEN
        self.source_channel = Config.SOURCE_CHANNEL_ID
        self.target_channel = Config.TARGET_CHANNEL_ID
        self.bot = telebot.TeleBot(self.bot_token, parse_mode='HTML')
        # Используем переданную БД или создаем новую
        self.db = database if database else NewsDatabase()
        self.scheduler = PublicationScheduler()
        self.urgent_keywords = Config.get_urgent_keywords()

        # Определяем время начала мониторинга
        monitor_from_date_str = Config.get_monitor_from_date()
        if monitor_from_date_str and monitor_from_date_str.strip():
            try:
                # Парсим дату из настроек
                self.bot_start_time = datetime.strptime(monitor_from_date_str, '%Y-%m-%d %H:%M:%S')
                # Добавляем timezone info
                self.bot_start_time = self.bot_start_time.replace(tzinfo=timezone.utc)
                logger.info(f"Дата мониторинга установлена из конфигурации: {self.bot_start_time}")
            except ValueError as e:
                logger.warning(f"Неверный формат даты в MONITOR_FROM_DATE: {monitor_from_date_str}. Используется время запуска бота. Ошибка: {e}")
                self.bot_start_time = datetime.now(timezone.utc)
        else:
            # Время запуска бота для фильтрации старых сообщений (если дата не указана)
            self.bot_start_time = datetime.now(timezone.utc)

        logger.info(f"Бот запущен. Будут обрабатываться только сообщения после {self.bot_start_time}")

        # Инициализация DeepSeek клиента с текущим стилем
        from deepseek_client import DeepSeekClient
        self.deepseek = DeepSeekClient()
        logger.info(f"DeepSeek инициализирован со стилем: {self.deepseek.get_style()}")

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

        @self.bot.message_handler(commands=['set_style', 'setstyle'])
        def cmd_set_style(message):
            self._cmd_set_style(message)

        @self.bot.message_handler(commands=['get_style', 'getstyle'])
        def cmd_get_style(message):
            self._cmd_get_style(message)

        @self.bot.message_handler(commands=['view'])
        def cmd_view(message):
            self._cmd_view(message)

        @self.bot.message_handler(commands=['config'])
        def cmd_config(message):
            self._cmd_config(message)

        @self.bot.message_handler(commands=['set_config', 'setconfig'])
        def cmd_set_config(message):
            self._cmd_set_config(message)

        @self.bot.message_handler(commands=['reload_config', 'reloadconfig'])
        def cmd_reload_config(message):
            self._cmd_reload_config(message)

        @self.bot.message_handler(commands=['settings'])
        def cmd_settings(message):
            self._cmd_settings(message)

        @self.bot.message_handler(commands=['rewrite'])
        def cmd_rewrite(message):
            self._cmd_rewrite(message)

        # Callback обработчик для inline кнопок
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_query(call):
            self._handle_callback_query(call)

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

        parser = NewsParser()

        for url in urls[:Config.MAX_ARTICLES_PER_RUN]:
            try:
                # Парсинг статьи
                article_data = parser.parse_article(url)

                if not article_data or not parser.validate_article(article_data):
                    logger.warning(f"Статья не прошла валидацию: {url}")
                    continue

                # Проверка срочности
                is_urgent = self.is_urgent_news(article_data.get('title', '') + ' ' + article_data.get('text', ''))

                # Обработка через DeepSeek с текущим стилем
                processed_text = self.deepseek.process_article(article_data)

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
                parse_mode='HTML',
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
        Заголовок делается жирным через HTML, остальное - простой текст

        Args:
            news: Данные новости из БД

        Returns:
            Отформатированный текст для HTML parse mode
        """
        import html

        processed_text = news.get('processed_text', '')
        url = news.get('url', '')

        # Разбиваем текст на строки
        lines = processed_text.split('\n')

        # Первая непустая строка - это заголовок
        title_line = ''
        body_lines = []
        title_found = False

        for line in lines:
            if not title_found and line.strip():
                # Это заголовок
                title_line = line.strip()
                title_found = True
            elif title_found:
                # Все после заголовка
                body_lines.append(line)

        # Экранируем HTML символы в заголовке и тексте
        title_escaped = html.escape(title_line)
        body_text = '\n'.join(body_lines).strip()
        body_escaped = html.escape(body_text)

        # Форматируем заголовок жирным
        formatted_title = f"<b>{title_escaped}</b>" if title_escaped else ""

        # Собираем финальный текст
        if formatted_title and body_escaped:
            final_text = f"{formatted_title}\n\n{body_escaped}"
        elif formatted_title:
            final_text = formatted_title
        else:
            final_text = body_escaped

        # Добавляем подпись канала и ссылку на источник (HTML формат)
        footer = f'\n\nКанал: @iberia_news\n<a href="{url}">Источник</a>'

        # Telegram имеет лимит в 4096 символов
        max_length = 4096 - len(footer) - 100  # запас

        if len(final_text) > max_length:
            final_text = final_text[:max_length] + "..."

        return final_text + footer


    # Команды управления ботом

    def _cmd_start(self, message: types.Message):
        """Команда /start"""
        start_time_str = self.bot_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')

        # Создаем inline клавиатуру
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("📊 Статус", callback_data="cmd_status"),
            types.InlineKeyboardButton("📋 Очередь", callback_data="cmd_queue")
        )
        keyboard.add(
            types.InlineKeyboardButton("❓ Помощь", callback_data="cmd_help"),
            types.InlineKeyboardButton("⚙️ Настройки", callback_data="cmd_settings")
        )

        self.bot.reply_to(
            message,
            "Бот автоматической публикации новостей запущен!\n\n"
            f"🕐 Время запуска: {start_time_str}\n"
            f"📡 Мониторинг канала: активен (только новые сообщения)\n\n"
            f"{self.scheduler.format_schedule()}\n\n"
            "Выберите действие:",
            parse_mode=None,
            reply_markup=keyboard
        )

    def _cmd_help(self, message: types.Message):
        """Команда /help"""
        available_styles = ', '.join(Config.AVAILABLE_STYLES)
        help_text = f"""
Доступные команды:

📋 Основные:
/start - Информация о боте
/status - Статус очереди новостей
/queue - Показать новости в очереди
/help - Это сообщение

⚙️ Настройки (админ):
/settings - Интерактивное меню настроек (кнопки)
/set_style [style] - Изменить стиль написания
/get_style - Показать текущий стиль
/config - Показать все настройки
/set_config [key] [value] - Изменить настройку
/reload_config - Перезагрузить настройки

📰 Публикации (админ):
/view [id] - Просмотр публикации по ID
/rewrite [id] - Переписать статью с новым стилем/длиной
/publishnow [id] - Опубликовать немедленно
/clear_queue - Очистить очередь

Доступные стили: {available_styles}
Доступные длины: short (1000), medium (2000), long (3000)
"""
        # Создаем inline клавиатуру
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("📊 Статус", callback_data="cmd_status"),
            types.InlineKeyboardButton("📋 Очередь", callback_data="cmd_queue")
        )
        keyboard.add(
            types.InlineKeyboardButton("⚙️ Настройки", callback_data="cmd_settings"),
            types.InlineKeyboardButton("📝 Текущий стиль", callback_data="cmd_get_style")
        )

        # Отправляем без HTML парсинга, так как это обычный текст
        self.bot.reply_to(message, help_text, parse_mode=None, reply_markup=keyboard)

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

            # Создаем inline клавиатуру
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("🔄 Обновить", callback_data="cmd_status"),
                types.InlineKeyboardButton("📋 Очередь", callback_data="cmd_queue")
            )
            keyboard.add(
                types.InlineKeyboardButton("⚙️ Настройки", callback_data="cmd_settings")
            )

            self.bot.reply_to(message, status_text, parse_mode=None, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка в команде /status: {e}")
            self.bot.reply_to(message, "Ошибка при получении статуса")

    def _cmd_queue(self, message: types.Message):
        """Команда /queue"""
        try:
            news_list = self.db.get_pending_news()

            if not news_list:
                keyboard = types.InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    types.InlineKeyboardButton("🔄 Обновить", callback_data="cmd_queue"),
                    types.InlineKeyboardButton("📊 Статус", callback_data="cmd_status")
                )
                self.bot.reply_to(message, "Очередь пуста", reply_markup=keyboard)
                return

            queue_text = f"📋 Новости в очереди ({len(news_list)}):\n\n"

            # Создаем inline клавиатуру с кнопками для первых 10 новостей
            keyboard = types.InlineKeyboardMarkup(row_width=2)

            for idx, news in enumerate(news_list[:10]):  # Показываем максимум 10 с кнопками
                urgent_mark = "🔥 " if news['is_urgent'] else ""
                queue_text += f"{urgent_mark}ID {news['id']}: {news['title'][:60]}...\n"
                queue_text += f"   ⏰ {news['scheduled_time']}\n"
                queue_text += f"   🔗 {news['url'][:50]}...\n\n"

                # Добавляем кнопки для каждой новости
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"👁️ Просмотр #{news['id']}",
                        callback_data=f"view_{news['id']}"
                    ),
                    types.InlineKeyboardButton(
                        f"🚀 Опубликовать #{news['id']}",
                        callback_data=f"publish_confirm_{news['id']}"
                    )
                )

            # Показываем оставшиеся новости без кнопок
            for news in news_list[10:20]:
                urgent_mark = "🔥 " if news['is_urgent'] else ""
                queue_text += f"{urgent_mark}ID {news['id']}: {news['title'][:60]}...\n"
                queue_text += f"   ⏰ {news['scheduled_time']}\n"
                queue_text += f"   🔗 {news['url'][:50]}...\n\n"

            if len(news_list) > 20:
                queue_text += f"\n... и еще {len(news_list) - 20} новостей"

            # Добавляем кнопки управления
            keyboard.add(
                types.InlineKeyboardButton("🔄 Обновить", callback_data="cmd_queue"),
                types.InlineKeyboardButton("📊 Статус", callback_data="cmd_status")
            )

            self.bot.reply_to(message, queue_text, parse_mode=None, reply_markup=keyboard)

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
                self.bot.reply_to(message, "Использование: /publishnow [id] или /publish_now [id]", parse_mode=None)
                return

            news_id = int(parts[1])
            logger.info(f"Запрос подтверждения публикации новости ID: {news_id}")

            # Получаем информацию о новости
            news = self.db.get_news_by_id(news_id)
            if not news:
                self.bot.reply_to(message, f"❌ Новость с ID {news_id} не найдена")
                return

            # Создаем inline клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton(
                    "✅ Да, опубликовать",
                    callback_data=f"publish_execute_{news_id}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="publish_cancel"
                )
            )

            self.bot.reply_to(
                message,
                f"🚀 **Подтверждение публикации**\n\n"
                f"Вы хотите опубликовать новость?\n\n"
                f"**ID:** {news_id}\n"
                f"**Заголовок:** {news.get('title', '')[:100]}...\n\n"
                f"Подтвердите действие:",
                parse_mode='Markdown',
                reply_markup=keyboard
            )

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

            # Получаем количество новостей в очереди
            stats = self.db.get_queue_status()
            pending_count = stats.get('pending', 0)

            if pending_count == 0:
                self.bot.reply_to(message, "Очередь уже пуста")
                return

            # Создаем inline клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton(
                    "✅ Да, очистить",
                    callback_data="clear_queue_execute"
                ),
                types.InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="clear_queue_cancel"
                )
            )

            self.bot.reply_to(
                message,
                f"⚠️ **Подтверждение очистки очереди**\n\n"
                f"Вы действительно хотите удалить **{pending_count}** новостей из очереди?\n\n"
                f"Это действие нельзя отменить!",
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Ошибка в команде /clear_queue: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_set_style(self, message: types.Message):
        """Команда /set_style <style> или /setstyle <style>"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /set_style от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Извлекаем стиль из команды
            parts = message.text.split()
            if len(parts) < 2:
                # Показываем меню с кнопками
                current_style = self.deepseek.get_style()

                keyboard = types.InlineKeyboardMarkup(row_width=1)

                style_names = {
                    'informative': '📰 Информативный',
                    'ironic': '😏 Ироничный',
                    'cynical': '😒 Циничный',
                    'playful': '😄 Шутливый',
                    'mocking': '🤣 Стебной'
                }

                for style_key, style_name in style_names.items():
                    checkmark = " ✓" if style_key == current_style else ""
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"{style_name}{checkmark}",
                            callback_data=f"style_{style_key}"
                        )
                    )

                self.bot.reply_to(
                    message,
                    f"📝 **Изменить стиль написания**\n\n"
                    f"Текущий стиль: **{current_style}**\n\n"
                    f"Выберите новый стиль:",
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                return

            new_style = parts[1].lower()

            # Проверяем доступность стиля
            if new_style not in Config.AVAILABLE_STYLES:
                available_styles = '\n'.join([f"- {style}" for style in Config.AVAILABLE_STYLES])
                self.bot.reply_to(
                    message,
                    f"❌ Неизвестный стиль: {new_style}\n\n"
                    f"Доступные стили:\n{available_styles}",
                    parse_mode=None
                )
                return

            # Устанавливаем новый стиль
            self.deepseek.set_style(new_style)
            logger.info(f"Стиль изменен на: {new_style}")

            self.bot.reply_to(
                message,
                f"✅ Стиль написания изменен на: {new_style}\n\n"
                f"Все новые статьи будут обрабатываться в этом стиле.",
                parse_mode=None
            )

        except Exception as e:
            logger.error(f"Ошибка в команде /set_style: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_get_style(self, message: types.Message):
        """Команда /get_style или /getstyle"""
        try:
            current_style = self.deepseek.get_style()
            available_styles = '\n'.join([f"- {style}" for style in Config.AVAILABLE_STYLES])

            # Создаем inline клавиатуру для быстрого изменения стиля
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            style_names = {
                'informative': '📰 Информативный',
                'ironic': '😏 Ироничный',
                'cynical': '😒 Циничный',
                'playful': '😄 Шутливый',
                'mocking': '🤣 Стебной'
            }

            for style_key, style_name in style_names.items():
                checkmark = " ✓" if style_key == current_style else ""
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"{style_name}{checkmark}",
                        callback_data=f"style_{style_key}"
                    )
                )

            self.bot.reply_to(
                message,
                f"📝 Текущий стиль написания: **{current_style}**\n\n"
                f"Выберите новый стиль:",
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Ошибка в команде /get_style: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_view(self, message: types.Message):
        """Команда /view <id> - просмотр публикации по ID"""
        try:
            # Извлекаем ID из команды
            parts = message.text.split()
            if len(parts) < 2:
                self.bot.reply_to(message, "Использование: /view [id]\n\nУкажите ID публикации для просмотра.", parse_mode=None)
                return

            news_id = int(parts[1])
            logger.info(f"Запрос на просмотр публикации ID: {news_id}")

            # Получаем новость из БД
            news = self.db.get_news_by_id(news_id)
            if not news:
                self.bot.reply_to(message, f"❌ Публикация с ID {news_id} не найдена")
                return

            # Форматируем текст для отображения
            final_text = self._format_for_telegram_from_db(news)

            # Добавляем информацию о статусе
            status_emoji = {
                'pending': '⏳',
                'published': '✅',
                'failed': '❌'
            }
            status = news.get('status', 'unknown')
            status_text = f"{status_emoji.get(status, '❓')} Статус: {status}\n"
            scheduled_text = f"⏰ Запланировано: {news.get('scheduled_time', 'не указано')}\n"
            updated_text = f"✏️ Изменено: {news.get('updated_at', 'не изменялось')}\n" if news.get('updated_at') else ""

            info_text = f"ID: {news_id}\n{status_text}{scheduled_text}{updated_text}\n{'='*30}\n\n"

            # Создаем inline клавиатуру с действиями
            keyboard = types.InlineKeyboardMarkup(row_width=2)

            # Если статья еще не опубликована, добавляем кнопки действий
            if status == 'pending':
                keyboard.add(
                    types.InlineKeyboardButton(
                        "🚀 Опубликовать",
                        callback_data=f"publish_confirm_{news_id}"
                    ),
                    types.InlineKeyboardButton(
                        "✏️ Переписать",
                        callback_data=f"rewrite_{news_id}_select_both"
                    )
                )
                keyboard.add(
                    types.InlineKeyboardButton(
                        "🗑️ Удалить",
                        callback_data=f"delete_confirm_{news_id}"
                    )
                )

            keyboard.add(
                types.InlineKeyboardButton("📋 Очередь", callback_data="cmd_queue"),
                types.InlineKeyboardButton("📊 Статус", callback_data="cmd_status")
            )

            # Отправляем превью публикации
            self.bot.reply_to(
                message,
                info_text + final_text,
                parse_mode='HTML',
                disable_web_page_preview=False,
                reply_markup=keyboard
            )

        except ValueError:
            self.bot.reply_to(message, "Неверный формат ID. Используйте: /view [id]", parse_mode=None)
        except Exception as e:
            logger.error(f"Ошибка в команде /view: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_config(self, message: types.Message):
        """Команда /config - показать все настройки бота"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /config от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Получаем все настройки из БД
            all_configs = self.db.get_all_config()

            if not all_configs:
                self.bot.reply_to(message, "⚠️ Нет настроек в базе данных", parse_mode=None)
                return

            # Форматируем список настроек
            config_text = "⚙️ **Настройки бота из базы данных:**\n\n"
            for key, value in all_configs.items():
                config_text += f"**{key}:** `{value}`\n"

            config_text += "\nИспользуйте /set_config для изменения или выберите настройку из меню:"

            # Создаем inline клавиатуру
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    "📝 Изменить стиль написания",
                    callback_data="settings_style"
                ),
                types.InlineKeyboardButton(
                    "📏 Изменить длину текста",
                    callback_data="settings_length"
                ),
                types.InlineKeyboardButton(
                    "🔄 Перезагрузить настройки",
                    callback_data="cmd_reload_config"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "⚙️ Интерактивные настройки",
                    callback_data="cmd_settings"
                )
            )

            self.bot.reply_to(message, config_text, parse_mode='Markdown', reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка в команде /config: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_set_config(self, message: types.Message):
        """Команда /set_config <key> <value> - установить настройку"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /set_config от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Извлекаем параметры из команды
            parts = message.text.split(maxsplit=2)
            if len(parts) < 3:
                self.bot.reply_to(
                    message,
                    "Использование: /set_config [key] [value]\n\n"
                    "Доступные настройки:\n"
                    "- PUBLISH_SCHEDULE (например: 8,12,16,20)\n"
                    "- URGENT_KEYWORDS (например: молния,breaking)\n"
                    "- MAX_ARTICLES_PER_RUN (например: 5)\n"
                    "- ARTICLE_STYLE (например: informative)\n"
                    "- CHECK_INTERVAL (например: 60)\n\n"
                    "Используйте /config для просмотра текущих настроек",
                    parse_mode=None
                )
                return

            key = parts[1]
            value = parts[2]

            # Обновляем настройку
            if Config.update_config(key, value):
                logger.info(f"Настройка {key} обновлена на: {value}")

                # Если это стиль - обновляем DeepSeek
                if key == 'ARTICLE_STYLE':
                    self.deepseek.set_style(value)

                # Если это ключевые слова - обновляем локальный кэш
                if key == 'URGENT_KEYWORDS':
                    self.urgent_keywords = Config.get_urgent_keywords()

                self.bot.reply_to(
                    message,
                    f"✅ Настройка обновлена:\n**{key}** = `{value}`\n\n"
                    f"⚠️ Некоторые изменения (например, PUBLISH_SCHEDULE) "
                    f"потребуют перезапуска бота для полного применения.",
                    parse_mode='Markdown'
                )
            else:
                self.bot.reply_to(message, f"❌ Ошибка при обновлении настройки {key}")

        except Exception as e:
            logger.error(f"Ошибка в команде /set_config: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_reload_config(self, message: types.Message):
        """Команда /reload_config - перезагрузить настройки из БД"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /reload_config от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Перезагружаем настройки из БД
            Config.reload_from_database()

            # Обновляем стиль в DeepSeek
            self.deepseek.set_style(Config.get_article_style())

            # Обновляем ключевые слова
            self.urgent_keywords = Config.get_urgent_keywords()

            logger.info("Настройки перезагружены из БД")

            self.bot.reply_to(
                message,
                f"✅ Настройки перезагружены из базы данных\n\n"
                f"Текущие настройки:\n"
                f"- PUBLISH_SCHEDULE: `{Config.PUBLISH_SCHEDULE}`\n"
                f"- ARTICLE_STYLE: `{Config.ARTICLE_STYLE}`\n"
                f"- URGENT_KEYWORDS: `{Config.URGENT_KEYWORDS}`\n"
                f"- MAX_ARTICLES_PER_RUN: `{Config.MAX_ARTICLES_PER_RUN}`\n\n"
                f"⚠️ Изменения в PUBLISH_SCHEDULE потребуют перезапуска бота",
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Ошибка в команде /reload_config: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_settings(self, message: types.Message):
        """Команда /settings - главное меню настроек с кнопками"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /settings от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Создаем inline клавиатуру с кнопками настроек
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            current_style = self.deepseek.get_style()
            current_length = Config.get_text_length()
            monitor_date = Config.get_monitor_from_date() or "С момента запуска"

            keyboard.add(
                types.InlineKeyboardButton(
                    f"📝 Стиль: {current_style}",
                    callback_data="settings_style"
                ),
                types.InlineKeyboardButton(
                    f"📏 Длина текста: {current_length}",
                    callback_data="settings_length"
                ),
                types.InlineKeyboardButton(
                    f"📅 Мониторить с: {monitor_date[:19]}",
                    callback_data="settings_date"
                )
            )

            settings_text = f"""
⚙️ **Настройки бота**

Текущие параметры:
• Стиль написания: `{current_style}`
• Длина текста: `{current_length}` ({Config.get_text_length_chars()} символов)
• Мониторинг с: `{monitor_date}`

Нажмите на кнопку для изменения настройки.
"""

            self.bot.reply_to(
                message,
                settings_text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Ошибка в команде /settings: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _cmd_rewrite(self, message: types.Message):
        """Команда /rewrite <id> - переписать статью с новым стилем/длиной"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"Команда /rewrite от пользователя ID: {user_id}")

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    logger.warning(f"Отказано в доступе для пользователя {user_id}")
                    self.bot.reply_to(
                        message,
                        f"❌ У вас нет прав для выполнения этой команды\n"
                        f"Ваш ID: {user_id}"
                    )
                    return
            else:
                logger.warning("ADMIN_USER_ID не установлен в конфиге - команда доступна всем!")

            # Извлекаем ID из команды
            parts = message.text.split()
            if len(parts) < 2:
                self.bot.reply_to(
                    message,
                    "Использование: /rewrite [id]\n\n"
                    "Укажите ID статьи для переписывания.\n"
                    "Пример: /rewrite 123",
                    parse_mode=None
                )
                return

            news_id = int(parts[1])
            logger.info(f"Запрос на переписывание статьи ID: {news_id}")

            # Получаем новость из БД
            news = self.db.get_news_by_id(news_id)
            if not news:
                self.bot.reply_to(message, f"❌ Статья с ID {news_id} не найдена")
                return

            # Показываем меню выбора параметров переписывания
            self._show_rewrite_menu(message, news_id)

        except ValueError:
            self.bot.reply_to(message, "Неверный формат ID. Используйте: /rewrite [id]", parse_mode=None)
        except Exception as e:
            logger.error(f"Ошибка в команде /rewrite: {e}")
            self.bot.reply_to(message, "Ошибка при выполнении команды")

    def _show_rewrite_menu(self, message: types.Message, news_id: int):
        """Показать меню выбора параметров для переписывания"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        current_style = self.deepseek.get_style()
        current_length = Config.get_text_length()

        keyboard.add(
            types.InlineKeyboardButton(
                "📝 Изменить только стиль",
                callback_data=f"rewrite_{news_id}_select_style_only"
            ),
            types.InlineKeyboardButton(
                "📏 Изменить только длину",
                callback_data=f"rewrite_{news_id}_select_length_only"
            ),
            types.InlineKeyboardButton(
                "🔄 Изменить стиль И длину",
                callback_data=f"rewrite_{news_id}_select_both"
            ),
            types.InlineKeyboardButton(
                "✅ Переписать с текущими настройками",
                callback_data=f"rewrite_{news_id}_confirm_current"
            )
        )

        menu_text = f"""
✏️ **Переписывание статьи ID {news_id}**

Текущие параметры:
• **Стиль**: {current_style}
• **Длина**: {current_length} ({Config.get_text_length_chars()} символов)

Выберите, что хотите изменить:
"""

        self.bot.reply_to(
            message,
            menu_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

    def _handle_callback_query(self, call):
        """Обработчик callback запросов от inline кнопок"""
        try:
            user_id = str(call.from_user.id)

            # Обработка команд навигации (доступны всем)
            if call.data == "cmd_status":
                self._handle_cmd_callback(call, self._cmd_status)
                return
            elif call.data == "cmd_queue":
                self._handle_cmd_callback(call, self._cmd_queue)
                return
            elif call.data == "cmd_help":
                self._handle_cmd_callback(call, self._cmd_help)
                return
            elif call.data == "cmd_settings":
                self._handle_cmd_callback(call, self._cmd_settings)
                return
            elif call.data == "cmd_get_style":
                self._handle_cmd_callback(call, self._cmd_get_style)
                return
            elif call.data == "cmd_reload_config":
                self._handle_cmd_callback(call, self._cmd_reload_config)
                return

            # Проверка прав администратора для остальных действий
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    self.bot.answer_callback_query(
                        call.id,
                        "❌ У вас нет прав для изменения настроек"
                    )
                    return

            # Обработка просмотра новостей
            if call.data.startswith("view_"):
                news_id = int(call.data.replace("view_", ""))
                self._handle_view_callback(call, news_id)
            # Обработка публикации
            elif call.data.startswith("publish_confirm_"):
                news_id = int(call.data.replace("publish_confirm_", ""))
                self._show_publish_confirmation(call, news_id)
            elif call.data.startswith("publish_execute_"):
                news_id = int(call.data.replace("publish_execute_", ""))
                self._execute_publish(call, news_id)
            elif call.data == "publish_cancel":
                self._handle_cancel_callback(call, "Публикация отменена")
            # Обработка удаления
            elif call.data.startswith("delete_confirm_"):
                news_id = int(call.data.replace("delete_confirm_", ""))
                self._show_delete_confirmation(call, news_id)
            elif call.data.startswith("delete_execute_"):
                news_id = int(call.data.replace("delete_execute_", ""))
                self._execute_delete(call, news_id)
            elif call.data == "delete_cancel":
                self._handle_cancel_callback(call, "Удаление отменено")
            # Обработка очистки очереди
            elif call.data == "clear_queue_execute":
                self._execute_clear_queue(call)
            elif call.data == "clear_queue_cancel":
                self._handle_cancel_callback(call, "Очистка очереди отменена")
            # Обработка настроек
            elif call.data == "settings_style":
                self._show_style_keyboard(call)
            elif call.data == "settings_length":
                self._show_length_keyboard(call)
            elif call.data == "settings_date":
                self._show_date_settings(call)
            elif call.data.startswith("style_"):
                self._set_style_from_callback(call)
            elif call.data.startswith("length_"):
                self._set_length_from_callback(call)
            elif call.data == "back_to_settings":
                self._show_settings_menu(call)
            # Обработка переписывания
            elif call.data.startswith("rewrite_"):
                self._handle_rewrite_callback(call)

        except Exception as e:
            logger.error(f"Ошибка в обработчике callback: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка при обработке запроса")

    def _show_style_keyboard(self, call):
        """Показать клавиатуру выбора стиля"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        style_names = {
            'informative': '📰 Информативный',
            'ironic': '😏 Ироничный',
            'cynical': '😒 Циничный',
            'playful': '😄 Шутливый',
            'mocking': '🤣 Стебной'
        }

        current_style = self.deepseek.get_style()

        for style_key, style_name in style_names.items():
            checkmark = " ✓" if style_key == current_style else ""
            keyboard.add(
                types.InlineKeyboardButton(
                    f"{style_name}{checkmark}",
                    callback_data=f"style_{style_key}"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton("← Назад", callback_data="back_to_settings")
        )

        self.bot.edit_message_text(
            "📝 **Выберите стиль написания:**\n\nСтиль применяется ко всем новым статьям.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id)

    def _show_length_keyboard(self, call):
        """Показать клавиатуру выбора длины текста"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        length_names = {
            'short': '📄 Короткий (1000 символов)',
            'medium': '📃 Средний (2000 символов)',
            'long': '📰 Длинный (3000 символов)'
        }

        current_length = Config.get_text_length()

        for length_key, length_name in length_names.items():
            checkmark = " ✓" if length_key == current_length else ""
            keyboard.add(
                types.InlineKeyboardButton(
                    f"{length_name}{checkmark}",
                    callback_data=f"length_{length_key}"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton("← Назад", callback_data="back_to_settings")
        )

        self.bot.edit_message_text(
            "📏 **Выберите длину текста:**\n\nДлина применяется ко всем новым статьям.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id)

    def _show_date_settings(self, call):
        """Показать настройки даты мониторинга"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("← Назад", callback_data="back_to_settings")
        )

        current_date = Config.get_monitor_from_date() or "Не установлена (с момента запуска)"

        instructions = f"""
📅 **Настройка даты мониторинга**

Текущая дата: `{current_date}`

Чтобы изменить дату мониторинга, используйте команду:
`/set_config MONITOR_FROM_DATE "YYYY-MM-DD HH:MM:SS"`

Примеры:
• `/set_config MONITOR_FROM_DATE "2025-01-01 00:00:00"`
• `/set_config MONITOR_FROM_DATE ""` (сбросить)

После изменения требуется перезапуск бота.
"""

        self.bot.edit_message_text(
            instructions,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id)

    def _set_style_from_callback(self, call):
        """Установить стиль из callback"""
        style = call.data.replace("style_", "")

        if style in Config.AVAILABLE_STYLES:
            # Обновляем стиль в DeepSeek
            self.deepseek.set_style(style)

            # Сохраняем в БД
            Config.update_config('ARTICLE_STYLE', style)

            self.bot.answer_callback_query(
                call.id,
                f"✅ Стиль изменен на: {style}"
            )

            # Обновляем меню
            self._show_settings_menu(call)
        else:
            self.bot.answer_callback_query(
                call.id,
                "❌ Неизвестный стиль"
            )

    def _set_length_from_callback(self, call):
        """Установить длину текста из callback"""
        length = call.data.replace("length_", "")

        if length in Config.AVAILABLE_TEXT_LENGTHS:
            # Сохраняем в БД
            Config.update_config('TEXT_LENGTH', length)

            chars = Config.AVAILABLE_TEXT_LENGTHS[length]
            self.bot.answer_callback_query(
                call.id,
                f"✅ Длина изменена на: {length} ({chars} символов)"
            )

            # Обновляем меню
            self._show_settings_menu(call)
        else:
            self.bot.answer_callback_query(
                call.id,
                "❌ Неизвестная длина"
            )

    def _show_settings_menu(self, call):
        """Показать главное меню настроек"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        current_style = self.deepseek.get_style()
        current_length = Config.get_text_length()
        monitor_date = Config.get_monitor_from_date() or "С момента запуска"

        keyboard.add(
            types.InlineKeyboardButton(
                f"📝 Стиль: {current_style}",
                callback_data="settings_style"
            ),
            types.InlineKeyboardButton(
                f"📏 Длина текста: {current_length}",
                callback_data="settings_length"
            ),
            types.InlineKeyboardButton(
                f"📅 Мониторить с: {monitor_date[:19]}",
                callback_data="settings_date"
            )
        )

        settings_text = f"""
⚙️ **Настройки бота**

Текущие параметры:
• Стиль написания: `{current_style}`
• Длина текста: `{current_length}` ({Config.get_text_length_chars()} символов)
• Мониторинг с: `{monitor_date}`

Нажмите на кнопку для изменения настройки.
"""

        self.bot.edit_message_text(
            settings_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id)

    def _handle_rewrite_callback(self, call):
        """Обработчик callback для переписывания статьи"""
        try:
            user_id = call.from_user.id
            username = call.from_user.username or "без username"

            data_parts = call.data.split("_")

            # Формат: rewrite_{news_id}_{action}[_{params}...]
            if len(data_parts) < 3:
                logger.warning(f"Неверный формат callback данных от пользователя {user_id} (@{username}): {call.data}")
                self.bot.answer_callback_query(call.id, "Ошибка: неверный формат данных")
                return

            news_id = int(data_parts[1])
            action = "_".join(data_parts[2:])  # Собираем все остальное в action

            logger.info(f"Пользователь {user_id} (@{username}) запросил rewrite для статьи {news_id}, действие: {action}")

            # Обработка разных типов действий
            if action == "select_style_only":
                # Показать меню выбора только стиля
                self._show_rewrite_style_menu(call, news_id, mode="style_only")
            elif action == "select_length_only":
                # Показать меню выбора только длины
                self._show_rewrite_length_menu(call, news_id, mode="length_only")
            elif action == "select_both":
                # Показать меню выбора стиля (первый шаг для обоих параметров)
                self._show_rewrite_style_menu(call, news_id, mode="both")
            elif action == "confirm_current":
                # Переписать с текущими настройками
                self._execute_rewrite(call, news_id, None, None)
            elif action.startswith("style_"):
                # Стиль выбран
                self._handle_style_selected(call, news_id, action)
            elif action.startswith("length_"):
                # Длина выбрана
                self._handle_length_selected(call, news_id, action)
            elif action.startswith("confirm_"):
                # Подтверждение переписывания
                self._handle_rewrite_confirm(call, news_id, action)
            else:
                logger.warning(f"Неизвестное действие rewrite от пользователя {user_id} (@{username}): {action}")
                self.bot.answer_callback_query(call.id, "Неизвестное действие")

        except Exception as e:
            logger.error(f"Ошибка в обработчике callback переписывания: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка при обработке запроса")

    def _show_rewrite_style_menu(self, call, news_id: int, mode: str = "style_only"):
        """
        Показать меню выбора стиля для переписывания
        mode: "style_only" - только стиль, "both" - стиль и длина
        """
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        style_names = {
            'informative': '📰 Информативный',
            'ironic': '😏 Ироничный',
            'cynical': '😒 Циничный',
            'playful': '😄 Шутливый',
            'mocking': '🤣 Стебной'
        }

        current_style = self.deepseek.get_style()

        for style_key, style_name in style_names.items():
            checkmark = " ✓" if style_key == current_style else ""
            # Callback data зависит от режима
            callback_data = f"rewrite_{news_id}_style_{style_key}_{mode}"
            keyboard.add(
                types.InlineKeyboardButton(
                    f"{style_name}{checkmark}",
                    callback_data=callback_data
                )
            )

        if mode == "both":
            prompt_text = f"📝 **Шаг 1/2: Выберите стиль для статьи ID {news_id}**\n\nТекущий стиль: {current_style}"
        else:
            prompt_text = f"📝 **Выберите новый стиль для статьи ID {news_id}:**\n\nТекущий стиль: {current_style}"

        self.bot.edit_message_text(
            prompt_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id)

    def _show_rewrite_length_menu(self, call, news_id: int, mode: str = "length_only", selected_style: str = None):
        """
        Показать меню выбора длины для переписывания
        mode: "length_only" - только длина, "both" - и стиль, и длина
        selected_style: уже выбранный стиль (для режима "both")
        """
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        length_names = {
            'short': '📄 Короткий (1000 символов)',
            'medium': '📃 Средний (2000 символов)',
            'long': '📰 Длинный (3000 символов)'
        }

        current_length = Config.get_text_length()

        for length_key, length_name in length_names.items():
            checkmark = " ✓" if length_key == current_length else ""
            # Callback data зависит от режима
            if mode == "both" and selected_style:
                callback_data = f"rewrite_{news_id}_length_{length_key}_with_style_{selected_style}"
            else:
                callback_data = f"rewrite_{news_id}_length_{length_key}_{mode}"
            keyboard.add(
                types.InlineKeyboardButton(
                    f"{length_name}{checkmark}",
                    callback_data=callback_data
                )
            )

        if mode == "both":
            prompt_text = f"📏 **Шаг 2/2: Выберите длину для статьи ID {news_id}**\n\n"
            if selected_style:
                prompt_text += f"Выбранный стиль: **{selected_style}**\n"
            prompt_text += f"Текущая длина: {current_length} ({Config.get_text_length_chars()} символов)"
        else:
            prompt_text = f"📏 **Выберите новую длину для статьи ID {news_id}:**\n\nТекущая длина: {current_length} ({Config.get_text_length_chars()} символов)"

        self.bot.edit_message_text(
            prompt_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id)

    def _handle_style_selected(self, call, news_id: int, action: str):
        """Обработка выбора стиля"""
        user_id = call.from_user.id
        username = call.from_user.username or "без username"

        # Парсим action: style_{style_name}_{mode}
        parts = action.split("_")
        if len(parts) < 3:
            logger.warning(f"Неверный формат action для выбора стиля от пользователя {user_id} (@{username}): {action}")
            self.bot.answer_callback_query(call.id, "Ошибка формата")
            return

        style_name = parts[1]  # Например: "ironic"
        mode = "_".join(parts[2:])  # Например: "style_only" или "both"

        logger.info(f"Пользователь {user_id} (@{username}) выбрал стиль '{style_name}' для статьи {news_id}, режим: {mode}")

        if mode == "style_only":
            # Только стиль - показываем подтверждение
            self._show_rewrite_confirmation(call, news_id, new_style=style_name, new_length=None)
        elif mode == "both":
            # Стиль и длина - переходим к выбору длины
            self._show_rewrite_length_menu(call, news_id, mode="both", selected_style=style_name)
        else:
            logger.warning(f"Неизвестный режим выбора стиля от пользователя {user_id} (@{username}): {mode}")
            self.bot.answer_callback_query(call.id, f"Неизвестный режим: {mode}")

    def _handle_length_selected(self, call, news_id: int, action: str):
        """Обработка выбора длины"""
        user_id = call.from_user.id
        username = call.from_user.username or "без username"

        # Парсим action: length_{length_name}_{mode} или length_{length_name}_with_style_{style_name}
        parts = action.split("_")
        if len(parts) < 3:
            logger.warning(f"Неверный формат action для выбора длины от пользователя {user_id} (@{username}): {action}")
            self.bot.answer_callback_query(call.id, "Ошибка формата")
            return

        length_name = parts[1]  # Например: "short"

        # Проверяем, есть ли уже выбранный стиль
        if "with" in action and "style" in action:
            # Формат: length_{length}_with_style_{style}
            try:
                style_idx = parts.index("style") + 1
                if style_idx < len(parts):
                    style_name = parts[style_idx]
                    logger.info(f"Пользователь {user_id} (@{username}) выбрал длину '{length_name}' и стиль '{style_name}' для статьи {news_id}")
                    # Оба параметра выбраны - показываем подтверждение
                    self._show_rewrite_confirmation(call, news_id, new_style=style_name, new_length=length_name)
                else:
                    logger.error(f"Стиль не найден в action от пользователя {user_id} (@{username}): {action}")
                    self.bot.answer_callback_query(call.id, "Ошибка: стиль не найден")
            except ValueError:
                logger.error(f"Ошибка парсинга стиля из action от пользователя {user_id} (@{username}): {action}")
                self.bot.answer_callback_query(call.id, "Ошибка: стиль не найден")
        else:
            # Только длина - показываем подтверждение
            logger.info(f"Пользователь {user_id} (@{username}) выбрал длину '{length_name}' для статьи {news_id}")
            self._show_rewrite_confirmation(call, news_id, new_style=None, new_length=length_name)

    def _show_rewrite_confirmation(self, call, news_id: int, new_style: str = None, new_length: str = None):
        """Показать подтверждение переписывания с выбранными параметрами"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        # Формируем callback_data для подтверждения
        if new_style and new_length:
            callback_data = f"rewrite_{news_id}_confirm_both_{new_style}_{new_length}"
            params_text = f"Новый стиль: **{new_style}**\nНовая длина: **{new_length}** ({Config.AVAILABLE_TEXT_LENGTHS.get(new_length, 2000)} символов)"
        elif new_style:
            callback_data = f"rewrite_{news_id}_confirm_style_{new_style}"
            params_text = f"Новый стиль: **{new_style}**\nДлина: **{Config.get_text_length()}** ({Config.get_text_length_chars()} символов)"
        elif new_length:
            callback_data = f"rewrite_{news_id}_confirm_length_{new_length}"
            params_text = f"Стиль: **{self.deepseek.get_style()}**\nНовая длина: **{new_length}** ({Config.AVAILABLE_TEXT_LENGTHS.get(new_length, 2000)} символов)"
        else:
            callback_data = f"rewrite_{news_id}_confirm_current"
            params_text = f"Стиль: **{self.deepseek.get_style()}**\nДлина: **{Config.get_text_length()}** ({Config.get_text_length_chars()} символов)"

        keyboard.add(
            types.InlineKeyboardButton(
                "✅ Переписать с этими параметрами",
                callback_data=callback_data
            ),
            types.InlineKeyboardButton(
                "❌ Отмена",
                callback_data=f"view_{news_id}"
            )
        )

        self.bot.edit_message_text(
            f"✏️ **Подтверждение переписывания статьи ID {news_id}**\n\n"
            f"{params_text}\n\n"
            f"Подтвердите переписывание:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        self.bot.answer_callback_query(call.id, "Параметры установлены")

    def _handle_rewrite_confirm(self, call, news_id: int, action: str):
        """Обработка подтверждения переписывания"""
        # Парсим action: confirm_{type}[_{params}]
        parts = action.split("_")
        if len(parts) < 2:
            self.bot.answer_callback_query(call.id, "Ошибка формата")
            return

        confirm_type = parts[1]  # "current", "style", "length", или "both"

        new_style = None
        new_length = None

        if confirm_type == "current":
            # Используем текущие настройки
            pass
        elif confirm_type == "style" and len(parts) >= 3:
            # Только новый стиль
            new_style = parts[2]
        elif confirm_type == "length" and len(parts) >= 3:
            # Только новая длина
            new_length = parts[2]
        elif confirm_type == "both" and len(parts) >= 4:
            # Оба параметра
            new_style = parts[2]
            new_length = parts[3]

        # Выполняем переписывание
        self._execute_rewrite(call, news_id, new_style, new_length)

    def _execute_rewrite(self, call, news_id: int, new_style: str = None, new_length: str = None):
        """
        Выполнить переписывание статьи

        Args:
            call: Callback query
            news_id: ID статьи
            new_style: Новый стиль (или None для текущего)
            new_length: Новая длина (или None для текущей)
        """
        try:
            user_id = call.from_user.id
            username = call.from_user.username or "без username"

            # ВАЖНО: Отвечаем на callback сразу, чтобы избежать timeout
            self.bot.answer_callback_query(call.id, "⏳ Начинаю переписывание...")

            # Получаем статью из БД
            news = self.db.get_news_by_id(news_id)
            if not news:
                logger.warning(f"Пользователь {user_id} (@{username}) запросил переписывание несуществующей статьи {news_id}")
                self.bot.edit_message_text(
                    f"❌ Статья {news_id} не найдена",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
                return

            # Используем текущие настройки, если новые не указаны
            style_to_use = new_style or self.deepseek.get_style()
            length_to_use = new_length or Config.get_text_length()

            logger.info(f"Пользователь {user_id} (@{username}) начал переписывание статьи {news_id}: стиль='{style_to_use}', длина='{length_to_use}'")

            # Показываем сообщение о начале переписывания
            self.bot.edit_message_text(
                f"⏳ **Переписываю статью ID {news_id}...**\n\n"
                f"Стиль: {style_to_use}\n"
                f"Длина: {length_to_use} ({Config.AVAILABLE_TEXT_LENGTHS.get(length_to_use, Config.get_text_length_chars())} символов)\n\n"
                f"Это может занять несколько секунд...",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown'
            )

            # Подготавливаем данные для переписывания
            article_data = {
                'title': news.get('title', ''),
                'text': news.get('original_text', '')
            }

            # Переписываем через DeepSeek
            rewritten_text = self.deepseek.rewrite_article(
                article_data,
                new_style=new_style,  # Передаем None если не изменяется
                text_length=new_length  # Передаем None если не изменяется
            )

            if rewritten_text:
                # Обновляем текст в БД
                success = self.db.update_processed_text(news_id, rewritten_text)

                if success:
                    chars = Config.AVAILABLE_TEXT_LENGTHS.get(length_to_use, Config.get_text_length_chars())
                    logger.info(f"✅ Пользователь {user_id} (@{username}) успешно переписал статью {news_id} (стиль: {style_to_use}, длина: {length_to_use})")
                    self.bot.edit_message_text(
                        f"✅ **Статья ID {news_id} успешно переписана!**\n\n"
                        f"Стиль: {style_to_use}\n"
                        f"Длина: {length_to_use} ({chars} символов)\n\n"
                        f"Используйте /view {news_id} для просмотра результата.",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        parse_mode='Markdown'
                    )
                else:
                    logger.error(f"❌ Ошибка при сохранении переписанной статьи {news_id} в БД для пользователя {user_id} (@{username})")
                    self.bot.edit_message_text(
                        f"❌ Ошибка при сохранении переписанной статьи в БД",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        parse_mode='Markdown'
                    )
            else:
                logger.error(f"❌ DeepSeek API не вернул текст при переписывании статьи {news_id} для пользователя {user_id} (@{username})")
                self.bot.edit_message_text(
                    f"❌ Ошибка при переписывании статьи через DeepSeek API",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Ошибка при выполнении переписывания статьи {news_id} для пользователя {user_id} (@{username}): {e}")
            try:
                self.bot.edit_message_text(
                    f"❌ **Ошибка при переписывании**\n\n{str(e)}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass  # Игнорируем ошибки редактирования сообщения

    # Вспомогательные методы для обработки callback

    def _handle_cmd_callback(self, call, cmd_func):
        """Обработка команд через callback"""
        try:
            # Создаем объект message из callback
            message = call.message
            # ВАЖНО: Заменяем from_user на реального пользователя, который нажал кнопку
            # call.message.from_user - это бот, call.from_user - это реальный пользователь
            message.from_user = call.from_user
            cmd_func(message)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при обработке команды через callback: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка при выполнении команды")

    def _handle_view_callback(self, call, news_id: int):
        """Обработка просмотра новости через callback"""
        try:
            logger.info(f"Просмотр новости ID: {news_id} через callback")

            # Получаем новость из БД
            news = self.db.get_news_by_id(news_id)
            if not news:
                self.bot.answer_callback_query(call.id, f"❌ Новость {news_id} не найдена")
                return

            # Форматируем текст для отображения
            final_text = self._format_for_telegram_from_db(news)

            # Добавляем информацию о статусе
            status_emoji = {
                'pending': '⏳',
                'published': '✅',
                'failed': '❌'
            }
            status = news.get('status', 'unknown')
            status_text = f"{status_emoji.get(status, '❓')} Статус: {status}\n"
            scheduled_text = f"⏰ Запланировано: {news.get('scheduled_time', 'не указано')}\n"
            updated_text = f"✏️ Изменено: {news.get('updated_at', 'не изменялось')}\n" if news.get('updated_at') else ""

            info_text = f"ID: {news_id}\n{status_text}{scheduled_text}{updated_text}\n{'='*30}\n\n"

            # Создаем inline клавиатуру с действиями
            keyboard = types.InlineKeyboardMarkup(row_width=2)

            # Если статья еще не опубликована, добавляем кнопки действий
            if status == 'pending':
                keyboard.add(
                    types.InlineKeyboardButton(
                        "🚀 Опубликовать",
                        callback_data=f"publish_confirm_{news_id}"
                    ),
                    types.InlineKeyboardButton(
                        "✏️ Переписать",
                        callback_data=f"rewrite_{news_id}_select_both"
                    )
                )
                keyboard.add(
                    types.InlineKeyboardButton(
                        "🗑️ Удалить",
                        callback_data=f"delete_confirm_{news_id}"
                    )
                )

            keyboard.add(
                types.InlineKeyboardButton("📋 Очередь", callback_data="cmd_queue"),
                types.InlineKeyboardButton("📊 Статус", callback_data="cmd_status")
            )

            # Отправляем новое сообщение (или редактируем текущее)
            try:
                self.bot.edit_message_text(
                    info_text + final_text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='HTML',
                    disable_web_page_preview=False,
                    reply_markup=keyboard
                )
            except:
                # Если не удалось отредактировать, отправляем новое сообщение
                self.bot.send_message(
                    call.message.chat.id,
                    info_text + final_text,
                    parse_mode='HTML',
                    disable_web_page_preview=False,
                    reply_markup=keyboard
                )

            self.bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Ошибка при просмотре новости через callback: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка при просмотре")

    def _show_publish_confirmation(self, call, news_id: int):
        """Показать подтверждение публикации"""
        try:
            # Получаем информацию о новости
            news = self.db.get_news_by_id(news_id)
            if not news:
                self.bot.answer_callback_query(call.id, f"❌ Новость {news_id} не найдена")
                return

            # Создаем inline клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton(
                    "✅ Да, опубликовать",
                    callback_data=f"publish_execute_{news_id}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="publish_cancel"
                )
            )

            self.bot.edit_message_text(
                f"🚀 **Подтверждение публикации**\n\n"
                f"Вы хотите опубликовать новость?\n\n"
                f"**ID:** {news_id}\n"
                f"**Заголовок:** {news.get('title', '')[:100]}...\n\n"
                f"Подтвердите действие:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown',
                reply_markup=keyboard
            )

            self.bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Ошибка при показе подтверждения публикации: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка")

    def _execute_publish(self, call, news_id: int):
        """Выполнить публикацию новости"""
        try:
            logger.info(f"Выполнение публикации новости ID: {news_id}")

            # ВАЖНО: Отвечаем на callback сразу, чтобы избежать timeout
            self.bot.answer_callback_query(call.id, "⏳ Публикую...")

            self.bot.edit_message_text(
                f"⏳ Публикую новость ID {news_id}...",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )

            success = self.publish_news_by_id(news_id)

            if success:
                self.bot.edit_message_text(
                    f"✅ **Новость успешно опубликована!**\n\nID: {news_id}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            else:
                self.bot.edit_message_text(
                    f"❌ **Ошибка при публикации новости**\n\nID: {news_id}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Ошибка при выполнении публикации через callback: {e}")
            try:
                self.bot.edit_message_text(
                    f"❌ **Ошибка при публикации**\n\n{str(e)}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass  # Игнорируем ошибки редактирования сообщения

    def _show_delete_confirmation(self, call, news_id: int):
        """Показать подтверждение удаления"""
        try:
            # Получаем информацию о новости
            news = self.db.get_news_by_id(news_id)
            if not news:
                self.bot.answer_callback_query(call.id, f"❌ Новость {news_id} не найдена")
                return

            # Создаем inline клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton(
                    "✅ Да, удалить",
                    callback_data=f"delete_execute_{news_id}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="delete_cancel"
                )
            )

            self.bot.edit_message_text(
                f"⚠️ **Подтверждение удаления**\n\n"
                f"Вы действительно хотите удалить новость?\n\n"
                f"**ID:** {news_id}\n"
                f"**Заголовок:** {news.get('title', '')[:100]}...\n\n"
                f"Это действие нельзя отменить!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown',
                reply_markup=keyboard
            )

            self.bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Ошибка при показе подтверждения удаления: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка")

    def _execute_delete(self, call, news_id: int):
        """Выполнить удаление новости"""
        try:
            logger.info(f"Удаление новости ID: {news_id}")

            # ВАЖНО: Отвечаем на callback сразу, чтобы избежать timeout
            self.bot.answer_callback_query(call.id, "⏳ Удаляю...")

            # Удаляем новость из БД
            success = self.db.delete_news(news_id)

            if success:
                self.bot.edit_message_text(
                    f"✅ **Новость удалена!**\n\nID: {news_id}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            else:
                self.bot.edit_message_text(
                    f"❌ **Ошибка при удалении новости**\n\nID: {news_id}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Ошибка при удалении новости через callback: {e}")
            try:
                self.bot.edit_message_text(
                    f"❌ **Ошибка при удалении**\n\n{str(e)}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass  # Игнорируем ошибки редактирования сообщения

    def _execute_clear_queue(self, call):
        """Выполнить очистку очереди"""
        try:
            logger.info("Выполнение очистки очереди")

            # ВАЖНО: Отвечаем на callback сразу, чтобы избежать timeout
            self.bot.answer_callback_query(call.id, "⏳ Очищаю...")

            success = self.db.clear_queue()

            if success:
                self.bot.edit_message_text(
                    "✅ **Очередь очищена!**\n\nВсе новости в ожидании были удалены.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            else:
                self.bot.edit_message_text(
                    "❌ **Ошибка при очистке очереди**",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Ошибка при очистке очереди через callback: {e}")
            try:
                self.bot.edit_message_text(
                    f"❌ **Ошибка при очистке очереди**\n\n{str(e)}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass  # Игнорируем ошибки редактирования сообщения

    def _handle_cancel_callback(self, call, message: str):
        """Обработка отмены действия"""
        try:
            self.bot.edit_message_text(
                f"✖️ {message}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
            self.bot.answer_callback_query(call.id, message)
        except Exception as e:
            logger.error(f"Ошибка при обработке отмены: {e}")
            self.bot.answer_callback_query(call.id, message)

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

    def set_webhook(self):
        """
        Установка webhook для получения обновлений от Telegram
        Требуется HTTPS URL
        """
        if not Config.WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL не установлен в конфигурации")

        webhook_url = Config.WEBHOOK_URL + Config.WEBHOOK_PATH
        logger.info(f"Установка webhook: {webhook_url}")

        try:
            self.bot.remove_webhook()
            logger.info("Предыдущий webhook удален")

            # Устанавливаем webhook
            self.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=False  # Не пропускаем ожидающие обновления
            )

            # Проверяем установку
            webhook_info = self.bot.get_webhook_info()
            logger.info(f"Webhook установлен успешно: {webhook_info.url}")
            logger.info(f"Ожидающих обновлений: {webhook_info.pending_update_count}")

            if webhook_info.last_error_date:
                logger.warning(f"Последняя ошибка webhook: {webhook_info.last_error_message}")

            return True
        except Exception as e:
            logger.error(f"Ошибка при установке webhook: {e}")
            raise

    def start_webhook(self):
        """
        Запуск бота в режиме webhook
        Не блокирует выполнение - webhook обрабатывается через Flask
        """
        logger.info("Запуск бота в режиме webhook")

        try:
            self.set_webhook()
            logger.info("Бот готов принимать обновления через webhook")
        except Exception as e:
            logger.error(f"Не удалось запустить webhook: {e}")
            raise

    def process_webhook_update(self, update_data: dict):
        """
        Обработка обновления от Telegram через webhook

        Args:
            update_data: JSON данные обновления от Telegram
        """
        try:
            # Преобразуем JSON в объект Update для telebot
            update = telebot.types.Update.de_json(update_data)

            # Обрабатываем обновление через bot
            self.bot.process_new_updates([update])

            logger.debug(f"Webhook обновление обработано: {update.update_id}")
        except Exception as e:
            logger.error(f"Ошибка при обработке webhook обновления: {e}", exc_info=True)
            raise

    def stop(self):
        """Остановка бота"""
        logger.info("Остановка бота")
        try:
            self.bot.stop_polling()
        except:
            pass  # Polling может не работать в webhook режиме
