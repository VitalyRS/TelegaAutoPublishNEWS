"""
Модуль для парсинга новостных статей
"""
import logging
from newspaper import Article
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class NewsParser:
    """Класс для извлечения контента из новостных статей"""

    @staticmethod
    def parse_article(url: str) -> Optional[Dict[str, str]]:
        """
        Парсинг статьи по URL

        Args:
            url: URL статьи

        Returns:
            Словарь с данными статьи или None в случае ошибки
        """
        try:
            article = Article(url)
            article.download()
            article.parse()

            # Попытка извлечь дополнительную информацию
            try:
                article.nlp()
            except Exception as e:
                logger.warning(f"Не удалось выполнить NLP обработку для {url}: {e}")

            result = {
                'title': article.title,
                'text': article.text,
                'authors': ', '.join(article.authors) if article.authors else 'Неизвестно',
                'publish_date': str(article.publish_date) if article.publish_date else 'Неизвестно',
                'top_image': article.top_image,
                'url': url,
                'summary': article.summary if hasattr(article, 'summary') else '',
                'keywords': ', '.join(article.keywords) if hasattr(article, 'keywords') else ''
            }

            logger.info(f"Успешно извлечена статья: {article.title}")
            return result

        except Exception as e:
            logger.error(f"Ошибка при парсинге статьи {url}: {e}")
            return None

    @staticmethod
    def validate_article(article_data: Dict[str, str], min_length: int = 100) -> bool:
        """
        Проверка валидности статьи

        Args:
            article_data: Данные статьи
            min_length: Минимальная длина текста

        Returns:
            True если статья валидна
        """
        if not article_data:
            return False

        if not article_data.get('text') or len(article_data['text']) < min_length:
            logger.warning(f"Статья слишком короткая или пустая: {article_data.get('url')}")
            return False

        if not article_data.get('title'):
            logger.warning(f"Статья без заголовка: {article_data.get('url')}")
            return False

        return True
