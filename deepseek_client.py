"""
Клиент для работы с DeepSeek API
"""
import logging
import requests
from typing import Optional, Dict
from config import Config

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Клиент для обработки текста через DeepSeek API"""

    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.api_url = Config.DEEPSEEK_API_URL
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

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
        prompt = f"""
Ты профессиональный редактор новостного портала. Твоя задача - обработать новостную статью следующим образом:

1. Перевести текст на русский язык (если он на другом языке)
2. Оформить в новостном стиле с четкой структурой
3. Разбить на абзацы для удобного чтения
4. Добавить подзаголовки где уместно
5. Выделить ключевые моменты
6. Использовать Markdown форматирование для Telegram:
   - **жирный текст** для важных моментов
   - *курсив* для акцентов
   - Списки где уместно

Исходная статья:

Заголовок: {article_data.get('title', '')}
Автор: {article_data.get('authors', 'Неизвестно')}
Дата: {article_data.get('publish_date', 'Неизвестно')}

Текст:
{article_data.get('text', '')}

Обработай эту статью согласно указанным требованиям. Результат должен быть готов к публикации в Telegram.
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
            payload = {
                'model': 'deepseek-chat',
                'messages': [
                    {
                        'role': 'system',
                        'content': 'Ты профессиональный редактор новостей. Твоя задача - обрабатывать и форматировать новостные статьи для публикации в Telegram.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'max_tokens': max_tokens,
                'temperature': 0.7,
                'stream': False
            }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=60
            )

            response.raise_for_status()
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                logger.error(f"Неожиданный формат ответа от API: {result}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при запросе к DeepSeek API: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при работе с DeepSeek API: {e}")
            return None
