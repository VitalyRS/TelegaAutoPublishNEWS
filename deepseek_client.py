"""
Клиент для работы с DeepSeek API
"""
import logging
from typing import Optional, Dict
from openai import OpenAI
from config import Config

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Клиент для обработки текста через DeepSeek API"""

    # Описания стилей написания
    STYLE_DESCRIPTIONS = {
        'informative': '''объективном журналистском стиле:
        - Нейтральный тон без эмоциональных оценок
        - Только факты: кто, что, где, когда, почему
        - Прямые утверждения без намеков
        - Структурированное изложение событий
        - Избегай субъективных мнений''',

        'ironic': '''ироничном стиле с явным сарказмом:
        - Используй кавычки для иронических эпитетов: "эффективные меры", "блестящее решение"
        - Риторические вопросы: "Кто бы мог подумать?", "Неожиданно, не правда ли?"
        - Контрастные сопоставления действий и результатов
        - Подчеркивай абсурдность через преувеличение
        - Иронические комментарии в скобках''',

        'cynical': '''циничном и недоверчивом стиле:
        - Подвергай сомнению все официальные заявления
        - Используй маркеры недоверия: "якобы", "по словам", "утверждается", "так называемый"
        - Указывай на возможные скрытые мотивы и интересы
        - Демонстрируй скептицизм к обещаниям властей
        - Намекай на коррупцию и манипуляции''',

        'playful': '''легком развлекательном стиле:
        - Разговорная речь и современный сленг
        - Неожиданные сравнения и яркие метафоры
        - Восклицательные предложения для динамики!
        - Шутливые комментарии и игра слов
        - Легкая ирония БЕЗ злого сарказма''',

        'mocking': '''стебно-сатирическом стиле:
        - Гиперболы и абсурдные преувеличения
        - Саркастические комментарии в скобках (конечно же!)
        - Пиши как для юмористической колонки
        - Высмеивай глупости и противоречия
        - Используй насмешливый тон и пародию'''
    }

    def __init__(self, style: str = None):
        self.api_key = Config.DEEPSEEK_API_KEY
        # DeepSeek API совместим с OpenAI, используем базовый URL DeepSeek
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        # Стиль написания (по умолчанию из конфига)
        self.style = style or Config.get_article_style()

    def process_article(self, article_data: Dict[str, str]) -> Optional[str]:
        """
        Обработка статьи через DeepSeek

        Args:
            article_data: Данные статьи

        Returns:
            Обработанный текст или None в случае ошибки
        """
        try:
            prompt = self._create_prompt(article_data)
            response = self._make_request(prompt)

            if response:
                logger.info(f"Успешно обработана статья: {article_data.get('title')}")
                return response
            else:
                logger.error("Не получен ответ от DeepSeek API")
                return None

        except Exception as e:
            logger.error(f"Ошибка при обработке статьи через DeepSeek: {e}")
            return None

    def _create_prompt(self, article_data: Dict[str, str]) -> str:
        """
        Создание промпта для DeepSeek

        Args:
            article_data: Данные статьи

        Returns:
            Промпт для API
        """
        style_description = self.STYLE_DESCRIPTIONS.get(self.style, self.STYLE_DESCRIPTIONS['informative'])

        # Получаем ограничение по длине текста
        text_length_chars = Config.get_text_length_chars()
        text_length_name = Config.get_text_length()

        prompt = f"""
Ты профессиональный редактор новостного портала. Твоя задача - обработать новостную статью следующим образом:

СТИЛЬ НАПИСАНИЯ: {style_description}

ОГРАНИЧЕНИЕ ПО ДЛИНЕ:
Длина текста должна быть {text_length_name.upper()} (примерно {text_length_chars} символов).
- Если short (1000 символов): краткое изложение основных фактов
- Если medium (2000 символов): стандартная статья с деталями
- Если long (3000 символов): подробная статья с расширенным контекстом

ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:
1. Перевести текст на русский язык (если он на другом языке)
2. Написать статью в указанном выше стиле
3. Разбить на абзацы для удобного чтения
4. ВАЖНО: НЕ использовать символы форматирования! Никаких *, _, **, __, #, `, ~ и других специальных символов для форматирования!
5. Писать простым текстом без какой-либо разметки
6. НЕ ВКЛЮЧАТЬ информацию об авторе или дате публикации
7. СТРОГО соблюдать ограничение по длине текста (~{text_length_chars} символов)

СТРУКТУРА ПУБЛИКАЦИИ:
1. ПЕРВАЯ СТРОКА - заголовок статьи (простой текст, без символов форматирования)
2. Пустая строка
3. Основной текст, разбитый на абзацы (длина основного текста ~{text_length_chars} символов)
4. В конце текста добавить раздел с тегами:

#тег1 #тег2 #тег3 #тег4 #тег5  #tag1_es #tag2_es #tag3_es #tag4_es #tag5_es

(Где тег1, тег2, тег3, #тег4, #тег5 - это теги на русском языке, а tag1_es, tag2_es, tag3_es, tag4_es, tag5_es - перевод этих же тегов на испанский язык)

ИСХОДНАЯ СТАТЬЯ:

Заголовок: {article_data.get('title', '')}

Текст:
{article_data.get('text', '')}

Обработай эту статью согласно ВСЕМ указанным требованиям. Результат должен быть готов к публикации в Telegram.
ВАЖНО:
- Используй только простой текст без символов форматирования! Заголовок должен быть на первой строке.
- ОБЯЗАТЕЛЬНО включи теги на русском и испанском в конце текста.
- НЕ забудь про стиль написания: {style_description}!
- СТРОГО соблюдай ограничение по длине: примерно {text_length_chars} символов для основного текста!
"""
        return prompt

    def _make_request(self, prompt: str, max_tokens: int = 4000) -> Optional[str]:
        """
        Отправка запроса к DeepSeek API

        Args:
            prompt: Промпт для обработки
            max_tokens: Максимальное количество токенов в ответе

        Returns:
            Текст ответа или None
        """
        try:
            response = self.client.chat.completions.create(
                model='deepseek-chat',
                messages=[
                    {
                        'role': 'system',
                        'content': 'Ты профессиональный редактор новостей с гибким стилем написания. '
                                   'Твоя задача - обрабатывать и форматировать новостные статьи для публикации в Telegram '
                                   'в различных стилях (информативный, ироничный, циничный, шутливый, стебной). '
                                   'ВСЕГДА добавляй теги на русском и испанском языках в конце статьи. '
                                   'НЕ используй символы # для заголовков, только **жирный текст**.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.8,
                stream=False
            )

            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            else:
                logger.error(f"Неожиданный формат ответа от API: {response}")
                return None

        except Exception as e:
            logger.error(f"Ошибка при работе с DeepSeek API: {e}")
            return None

    def set_style(self, style: str):
        """
        Установить новый стиль написания

        Args:
            style: Название стиля
        """
        if style.lower() in Config.AVAILABLE_STYLES:
            self.style = style.lower()
            logger.info(f"Стиль изменен на: {self.style}")
        else:
            logger.warning(f"Неизвестный стиль: {style}. Доступны: {', '.join(Config.AVAILABLE_STYLES)}")

    def get_style(self) -> str:
        """Получить текущий стиль написания"""
        return self.style

    def rewrite_article(self, article_data: Dict[str, str], new_style: str = None,
                       text_length: str = None) -> Optional[str]:
        """
        Переписать статью с новым стилем и/или длиной текста

        Args:
            article_data: Данные статьи (должны содержать 'title' и 'text')
            new_style: Новый стиль написания (если None - использовать текущий)
            text_length: Длина текста ('short', 'medium', 'long', если None - использовать текущую)

        Returns:
            Переписанный текст или None в случае ошибки
        """
        try:
            # Временно сохраняем текущий стиль
            original_style = self.style

            # Устанавливаем новый стиль если указан
            if new_style:
                self.style = new_style

            # Создаем промпт с указанной длиной или текущей
            prompt = self._create_rewrite_prompt(article_data, text_length)

            # Делаем запрос
            response = self._make_request(prompt)

            # Восстанавливаем оригинальный стиль
            self.style = original_style

            if response:
                logger.info(f"Успешно переписана статья: {article_data.get('title')} "
                          f"(стиль: {new_style or original_style}, длина: {text_length or 'текущая'})")
                return response
            else:
                logger.error("Не получен ответ от DeepSeek API при переписывании")
                return None

        except Exception as e:
            # Восстанавливаем оригинальный стиль в случае ошибки
            self.style = original_style
            logger.error(f"Ошибка при переписывании статьи через DeepSeek: {e}")
            return None

    def _create_rewrite_prompt(self, article_data: Dict[str, str], text_length: str = None) -> str:
        """
        Создание промпта для переписывания статьи

        Args:
            article_data: Данные статьи
            text_length: Желаемая длина текста

        Returns:
            Промпт для API
        """
        from config import Config

        style_description = self.STYLE_DESCRIPTIONS.get(self.style, self.STYLE_DESCRIPTIONS['informative'])

        # Получаем ограничение по длине текста
        if text_length:
            # Используем указанную длину
            length_chars = Config.AVAILABLE_TEXT_LENGTHS.get(text_length, 2000)
            length_name = text_length
        else:
            # Используем текущую настройку
            length_chars = Config.get_text_length_chars()
            length_name = Config.get_text_length()

        prompt = f"""
Ты профессиональный редактор новостного портала. Твоя задача - ПЕРЕПИСАТЬ существующую статью в новом стиле и/или с новой длиной.

СТИЛЬ НАПИСАНИЯ: {style_description}

ОГРАНИЧЕНИЕ ПО ДЛИНЕ:
Длина текста должна быть {length_name.upper()} (примерно {length_chars} символов).
- Если short (1000 символов): краткое изложение основных фактов
- Если medium (2000 символов): стандартная статья с деталями
- Если long (3000 символов): подробная статья с расширенным контекстом

ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:
1. Переписать статью в указанном выше стиле
2. Разбить на абзацы для удобного чтения
3. ВАЖНО: НЕ использовать символы форматирования! Никаких *, _, **, __, #, `, ~ и других специальных символов для форматирования!
4. Писать простым текстом без какой-либо разметки
5. НЕ ВКЛЮЧАТЬ информацию об авторе или дате публикации
6. СТРОГО соблюдать ограничение по длине текста (~{length_chars} символов)

СТРУКТУРА ПУБЛИКАЦИИ:
1. ПЕРВАЯ СТРОКА - заголовок статьи (простой текст, без символов форматирования)
2. Пустая строка
3. Основной текст, разбитый на абзацы (длина основного текста ~{length_chars} символов)
4. В конце текста добавить раздел с тегами:

#тег1 #тег2 #тег3 #tag1_es #tag2_es #tag3_es

(Где тег1, тег2, тег3 - это теги на русском языке, а tag1_es, tag2_es, tag3_es - перевод этих же тегов на испанский язык)

ИСХОДНАЯ СТАТЬЯ:

Заголовок: {article_data.get('title', '')}

Текст:
{article_data.get('text', '')}

Перепиши эту статью согласно ВСЕМ указанным требованиям. Результат должен быть готов к публикации в Telegram.
ВАЖНО:
- Используй только простой текст без символов форматирования! Заголовок должен быть на первой строке.
- ОБЯЗАТЕЛЬНО включи теги на русском и испанском в конце текста.
- НЕ забудь про стиль написания: {style_description}!
- СТРОГО соблюдай ограничение по длине: примерно {length_chars} символов для основного текста!
"""
        return prompt
