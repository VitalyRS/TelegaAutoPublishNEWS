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
        'informative': 'информативном и нейтральном стиле, предоставляя факты четко и объективно',
        'ironic': 'ироничном стиле, используя тонкую иронию и намеки',
        'cynical': 'циничном стиле, демонстрируя скептицизм и критический взгляд',
        'playful': 'шутливом стиле, используя легкий юмор и игривые формулировки',
        'mocking': 'стебном стиле, используя сатиру и едкий сарказм'
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

        prompt = f"""
Ты профессиональный редактор новостного портала. Твоя задача - обработать новостную статью следующим образом:

СТИЛЬ НАПИСАНИЯ: {style_description}

ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:
1. Перевести текст на русский язык (если он на другом языке)
2. Написать статью в указанном выше стиле
3. Разбить на абзацы для удобного чтения
4. ВАЖНО: НЕ использовать символы # для заголовков! Вместо этого используй **жирный текст**
5. Использовать Markdown форматирование для Telegram:
   - **жирный текст** для заголовков и важных моментов
   - *курсив* для акцентов
   - Списки где уместно
6. НЕ ВКЛЮЧАТЬ информацию об авторе или дате публикации

СТРУКТУРА ПУБЛИКАЦИИ:
1. Заголовок статьи (используй **жирный текст**, НЕ используй символы #)
2. Основной текст с подзаголовками (подзаголовки тоже **жирным**, без #)
3. В конце текста добавить раздел с тегами:

**Теги:**
#тег1 #тег2 #тег3

**Tags:**
#tag1_es #tag2_es #tag3_es

(Где тег1, тег2, тег3 - это теги на русском языке, а tag1_es, tag2_es, tag3_es - перевод этих же тегов на испанский язык)

ИСХОДНАЯ СТАТЬЯ:

Заголовок: {article_data.get('title', '')}

Текст:
{article_data.get('text', '')}

Обработай эту статью согласно ВСЕМ указанным требованиям. Результат должен быть готов к публикации в Telegram.
ОБЯЗАТЕЛЬНО включи теги на русском и испанском в конце текста.
НЕ забудь про стиль написания: {style_description}!
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
