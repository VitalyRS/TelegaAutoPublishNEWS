"""
Юнит-тесты для клиента DeepSeek API (deepseek_client.py)
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from deepseek_client import DeepSeekClient


class TestDeepSeekClient(unittest.TestCase):

    def setUp(self):
        Config.DEEPSEEK_API_KEY = "test-key"
        Config.DEEPSEEK_MODEL = "deepseek-v4-flash"

    def test_model_sanitization_default(self):
        """Проверка, что по умолчанию выбирается deepseek-v4-flash"""
        client = DeepSeekClient()
        self.assertEqual(getattr(Config, 'DEEPSEEK_MODEL', 'deepseek-v4-flash'), 'deepseek-v4-flash')

    def test_model_sanitization_invalid_model_fallback(self):
        """Проверка, что при попытке передать deepseek-chat или ошибочное имя используется deepseek-v4-flash"""
        Config.DEEPSEEK_MODEL = "deepseek-chat"
        client = DeepSeekClient()

        # Мокаем openai client.chat.completions.create
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"processed_text": "Заголовок\\n\\nТекст", "topic_id": 1}'))]
        client.client.chat.completions.create = MagicMock(return_value=mock_response)

        res = client.process_article({"title": "Тест", "text": "Текст статьи"})
        self.assertIsNotNone(res)

        # Проверяем, что в kwargs для create передалось именно 'deepseek-v4-flash'
        called_kwargs = client.client.chat.completions.create.call_args[1]
        self.assertEqual(called_kwargs['model'], 'deepseek-v4-flash')

    def test_model_sanitization_pro_model(self):
        """Проверка, что deepseek-v4-pro корректно разрешена"""
        Config.DEEPSEEK_MODEL = "deepseek-v4-pro"
        client = DeepSeekClient()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"processed_text": "Заголовок\\n\\nТекст", "topic_id": 2}'))]
        client.client.chat.completions.create = MagicMock(return_value=mock_response)

        res = client.process_article({"title": "Тест", "text": "Текст статьи"})
        self.assertIsNotNone(res)
        called_kwargs = client.client.chat.completions.create.call_args[1]
        self.assertEqual(called_kwargs['model'], 'deepseek-v4-pro')

    def test_response_format_error_fallback(self):
        """Проверка повторной попытки без response_format при возникновении ошибки"""
        Config.DEEPSEEK_MODEL = "deepseek-v4-flash"
        client = DeepSeekClient()

        mock_success_response = MagicMock()
        mock_success_response.choices = [MagicMock(message=MagicMock(content='{"processed_text": "Успех", "topic_id": 1}'))]

        # Первый вызов выбрасывает ошибку (например 400 Bad Request на response_format), второй проходит успешно
        client.client.chat.completions.create = MagicMock(
            side_effect=[Exception("400 Bad Request on response_format"), mock_success_response]
        )

        res = client.process_article({"title": "Тест", "text": "Текст статьи"})
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "Успех")
        self.assertEqual(client.client.chat.completions.create.call_count, 2)

    def test_api_unsupported_model_name_retry(self):
        """Проверка повторной попытки с переключением на deepseek-v4-flash при ошибке 'supported API model names'"""
        Config.DEEPSEEK_MODEL = "deepseek-v4-pro"
        client = DeepSeekClient()

        mock_success_response = MagicMock()
        mock_success_response.choices = [MagicMock(message=MagicMock(content='{"processed_text": "Фолбэк текст", "topic_id": 3}'))]

        error_msg = "Error code: 400 - {'error': {'message': 'The supported API model names are deepseek-v4-pro or deepseek-v4-flash, but you passed invalid-model.'}}"

        client.client.chat.completions.create = MagicMock(
            side_effect=[Exception(error_msg), mock_success_response]
        )

        res = client.process_article({"title": "Тест", "text": "Текст статьи"})
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "Фолбэк текст")
        self.assertEqual(client.client.chat.completions.create.call_count, 2)


if __name__ == '__main__':
    unittest.main()
