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
        self.bot.reply_to(
            message,
            "Бот автоматической публикации новостей запущен!\n\n"
            f"🕐 Время запуска: {start_time_str}\n"
            f"📡 Мониторинг канала: активен (только новые сообщения)\n\n"
            f"{self.scheduler.format_schedule()}\n\n"
            "Используйте /help для списка команд.",
            parse_mode=None
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
/publishnow [id] - Опубликовать немедленно
/clear_queue - Очистить очередь

Доступные стили: {available_styles}
Доступные длины: short (1000), medium (2000), long (3000)
"""
        # Отправляем без HTML парсинга, так как это обычный текст
        self.bot.reply_to(message, help_text, parse_mode=None)

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

            self.bot.reply_to(message, status_text, parse_mode=None)

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

            self.bot.reply_to(message, queue_text, parse_mode=None)

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
                available_styles = '\n'.join([f"- {style}" for style in Config.AVAILABLE_STYLES])
                self.bot.reply_to(
                    message,
                    f"Использование: /set_style [style] или /setstyle [style]\n\n"
                    f"Доступные стили:\n{available_styles}\n\n"
                    f"Текущий стиль: {self.deepseek.get_style()}",
                    parse_mode=None
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

            self.bot.reply_to(
                message,
                f"📝 Текущий стиль написания: {current_style}\n\n"
                f"Доступные стили:\n{available_styles}\n\n"
                f"Чтобы изменить стиль, используйте: /set_style [style]",
                parse_mode=None
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

            info_text = f"ID: {news_id}\n{status_text}{scheduled_text}\n{'='*30}\n\n"

            # Отправляем превью публикации
            self.bot.reply_to(
                message,
                info_text + final_text,
                parse_mode='HTML',
                disable_web_page_preview=False
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

            config_text += "\nИспользуйте /set_config для изменения настроек"

            self.bot.reply_to(message, config_text, parse_mode='Markdown')

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

    def _handle_callback_query(self, call):
        """Обработчик callback запросов от inline кнопок"""
        try:
            user_id = str(call.from_user.id)

            # Проверка прав администратора
            if Config.ADMIN_USER_ID:
                if user_id != Config.ADMIN_USER_ID:
                    self.bot.answer_callback_query(
                        call.id,
                        "❌ У вас нет прав для изменения настроек"
                    )
                    return

            # Обработка разных типов callback
            if call.data == "settings_style":
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
