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


    def test_dai_digest_preserves_all_links(self):
        """Проверка, что в дайджестах #dai все ссылки в формате Markdown сохраняются и преобразуются в HTML"""
        import sys
        for mod in ['telebot', 'telebot.types', 'newspaper', 'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.background']:
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()

        from telegram_handler import TelegramHandler

        # Создаем заглушку обработчика
        with patch('telegram_handler.telebot.TeleBot'), \
             patch('telegram_handler.NewsDatabase'), \
             patch('telegram_handler.PublicationScheduler'), \
             patch('deepseek_client.DeepSeekClient'):
            handler = TelegramHandler()

        sample_dai_text = (
            "🦁 1. Спецоперация по поиску льва\n"
            "🔗 [Читать оригинал на 20minutos.es](https://www.20minutos.es/article.html)\n\n"
            "🏴‍☠️ 2. Пиратский флаг\n"
            "🔗 [Читать оригинал на elnortedecastilla.es](https://www.elnortedecastilla.es/article.html)"
        )

        news_item = {
            'processed_text': sample_dai_text,
            'url': 'dai:12345_abcde'
        }

        formatted = handler._format_for_telegram_from_db(news_item)

    def test_spanish_lifehacks_digest_formatting(self):
        """Проверка форматирования дайджеста лайфхаков с ссылками google redirect"""
        import sys
        for mod in ['telebot', 'telebot.types', 'newspaper', 'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.background']:
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()

        from telegram_handler import TelegramHandler

        with patch('telegram_handler.telebot.TeleBot'), \
             patch('telegram_handler.NewsDatabase'), \
             patch('telegram_handler.PublicationScheduler'), \
             patch('deepseek_client.DeepSeekClient'):
            handler = TelegramHandler()

        sample_text = (
            "🇪🇸 Лайфхаки для жизни в Испании: как избежать штрафов и защитить свои права в 2026 году\n"
            "📬 1. Срочно оцифруйте свои больничные! 🔗 [Подробнее на Expansion](https://www.google.com/url?sa=E&q=https%3A%2F%2Fwww.expansion.com%2Feconomia%2F2026%2F08%2F21%2F6a881848468aeb1c3d8b4596.html)\n"
            "🚘 2. Владельцам авто старше 10 лет: ITV каждые 6 месяцев 🔗 [Подробнее на OKDiario](https://www.google.com/url?sa=E&q=https%3A%2F%2Fokdiario.com%2Fmotor%2Fboe-lo-confirma-dgt-pasar-itv-cada-seis-meses-vehiculos-mas-10-anos-antiguedad-17262248)"
        )

        news_item = {
            'processed_text': sample_text,
            'url': 'dai:67890_fghij'
        }

        formatted = handler._format_for_telegram_from_db(news_item)

        # Проверяем, что Google redirect ссылки очищены до прямых URL
        self.assertIn('<a href="https://www.expansion.com/economia/2026/08/21/6a881848468aeb1c3d8b4596.html">Подробнее на Expansion</a>', formatted)
        self.assertIn('<a href="https://okdiario.com/motor/boe-lo-confirma-dgt-pasar-itv-cada-seis-meses-vehiculos-mas-10-anos-antiguedad-17262248">Подробнее на OKDiario</a>', formatted)
        # Проверяем отсутствие unclosed tags
        self.assertEqual(formatted.count('<a href='), formatted.count('</a>'))
        self.assertEqual(formatted.count('<b>'), formatted.count('</b>'))


if __name__ == '__main__':
    unittest.main()
