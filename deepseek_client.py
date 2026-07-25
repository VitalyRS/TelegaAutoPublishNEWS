"""
Клиент для работы с DeepSeek API
"""
import json
import logging
from typing import Optional, Dict, Tuple
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

    def process_article(self, article_data: Dict[str, str]) -> Optional[Tuple[str, Optional[int]]]:
        """
        Обработка статьи через DeepSeek

        Args:
            article_data: Данные статьи

        Returns:
            Tuple (Обработанный текст, ID топика) или None в случае ошибки
        """
        try:
            system_prompt, prompt = self._create_prompt(article_data)
            response_text = self._make_request(prompt, expect_json=True, system_prompt=system_prompt)

            if response_text:
                try:
                    # Ожидаем JSON ответ: {"processed_text": "...", "topic_id": 1}
                    data = json.loads(response_text)
                    processed_text = data.get('processed_text')
                    topic_id = data.get('topic_id')
                    
                    # Если категория не определена (null), помещаем в 3 #life
                    if topic_id is None:
                        topic_id = 3
                        
                    if not processed_text:
                        logger.error("JSON ответ от DeepSeek не содержит 'processed_text'")
                        return None
                        
                    logger.info(f"Успешно обработана статья: {article_data.get('title')} (Topic: {topic_id})")
                    return processed_text, topic_id
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка при разборе JSON от DeepSeek: {e}. Ответ: {response_text[:200]}...")
                    return None
            else:
                logger.error("Не получен ответ от DeepSeek API")
                return None

        except Exception as e:
            logger.error(f"Ошибка при обработке статьи через DeepSeek: {e}")
            return None

    def _create_system_prompt(self, style_description: str, text_length_chars: int, text_length_name: str) -> str:
        """Создает системный промпт с правилами форматирования"""
        return f"""
Ты профессиональный редактор новостного портала. Твоя задача - обработать новостную статью следующим образом:

СТИЛЬ НАПИСАНИЯ: {style_description}

ОГРАНИЧЕНИЕ ПО ДЛИНЕ:
Длина текста должна быть {text_length_name.upper()} (примерно {text_length_chars} символов).
- Если short (1000 символов): краткое изложение основных фактов
- Если medium (2000 символов): стандартная статья с деталями
- Если long (3000 символов): подробная статья с расширенным контекстом

ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:
1. КРИТИЧЕСКИ ВАЖНО: ПЕРЕВЕСТИ ВЕСЬ ТЕКСТ НА РУССКИЙ ЯЗЫК. Весь итоговый результат (заголовок и основной текст) должен быть ИСКЛЮЧИТЕЛЬНО на русском языке, независимо от языка оригинала!
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

КЛАССИФИКАЦИЯ (КАТЕГОРИИ):
категорию новости нужно сделать так Выбери НАИБОЛЕЕ подходящую категорию (от 1 до 7 а это категории 1: #news,2: #visa,3:#life,4:#spanish,5:#tourism,6:#family,7:#about_us) для этой новости. Если новость не подходит ни под одну из категорий, верни null и помести эту новость в 3 #life.
1: #news Важные Новости и Налоги — Официально: Законы из BOE, налоги (Modelo 100/721), банковские лимиты.
    Только важные новости, Налоги, банковские законы, жилье и аренда, забастовки, транспортный сектор (ВНИМАНИЕ: Политика сюда НЕ входит, отправляй политику в #life)
2: #visa ВНЖ и Амнистия 2026, Гражданство — Все виды Arraigo, Гражданство и инструкции по Амнистии (подача до 30.06.26).
    1. Блок «Амнистия и Чрезвычайная легализация» (Regularización 2026)
    2. Блок «Цифровые кочевники» (Digital Nomad / Nómada Digital)
    3. Блок «Типы ВНЖ и Резиденции» (Tipos de Residencia)
    4. Блок «Бюрократия: Ситы и Карточки» (Citas y Huellas)
    5. Блок «Сроки и Очереди» (Plazos y Expedientes)
3:#life Жизнь, Политика и Общество — Праздники, культура, политика, социальные темы, интересные факты.
    1. Праздники и события (Fiestas y Eventos)
    2. Культура и Традиции (Cultura)
    3. История и Регионы (Historia y Regiones)
    4. Интересные факты и «Секретные места» (Curiosidades)
    5. Политика (Política) — любые политические новости, решения партий, выборы
    6. Общество (Sociedad) — социальные проблемы, общественные инициативы, жизнь людей
4:#spanish Учим Испанский — Сленг, фразы для жизни, курсы и подготовка к экзаменам.
    1. Сленг и «Живой» язык (Español Coloquial)
    2. Фразы для жизни (Español para la Vida)
    3. Экзамены и Сертификаты (DELE / SIELE)
    4. Курсы и Обучение (Cursos y Recursos)
    5. Грамматика и Фонетика (Gramática y Pronunciación)
5:#tourism Туризм и Рестораны — Маршруты, лучшие тапас-бары, пляжи и планы на выходные.
    1. Гастрономия и Рестораны (Gastronomía)
    2. Туризм и Маршруты (Turismo y Rutas)
    3. Пляжи и Море (Playas y Costas)
    4. Отели и Жилье (Alojamiento)
    5. Лайфхаки и Секретные места (Hidden Gems)
6:#family Семья и Здоровье — Школы, садики, запись к врачам (SIP), пособия и страховки.
    1. Здравоохранение и медицина (Salud)
    2. Страхование (Seguros Médicos)
    3. Школы и Детские сады (Educación Infantil y Colegio)
    4. Пособия и Социальная помощь (Ayudas и Subvenciones)
    5. Административные шаги (Tramites Familiares)
7:#about_us Новости о нас — Новости проекта, обновления, важные объявления от администрации.

ВАЖНО:
- ТВОЙ ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON! Никакого лишнего текста.
- ВЕСЬ ТЕКСТ НОВОСТИ (заголовок и тело) ДОЛЖЕН БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ!
- Формат JSON: `{{"processed_text": "полный текст со структурой и тегами", "topic_id": 1}}` или `null` вместо 1, если нет подходящей.
- В поле "processed_text" используй только простой текст без символов форматирования markdown! Заголовок должен быть на первой строке.
- ОБЯЗАТЕЛЬНО включи теги на русском и испанском в конце текста "processed_text".
- НЕ забудь про стиль написания: {style_description}!
- СТРОГО соблюдай ограничение по длине "processed_text": примерно {text_length_chars} символов для основного текста!
"""

    def _create_prompt(self, article_data: Dict[str, str]) -> tuple[str, str]:
        """
        Создание промпта для DeepSeek

        Args:
            article_data: Данные статьи

        Returns:
            Системный и пользовательский промпт для API
        """
        style_description = self.STYLE_DESCRIPTIONS.get(self.style, self.STYLE_DESCRIPTIONS['informative'])

        # Получаем ограничение по длине текста
        text_length_chars = Config.get_text_length_chars()
        text_length_name = Config.get_text_length()

        system_prompt = self._create_system_prompt(style_description, text_length_chars, text_length_name)

        # Промпт перенесен в system prompt
        prompt = f"""ИСХОДНАЯ СТАТЬЯ:

Заголовок: {article_data.get('title', '')}

Текст:
{article_data.get('text', '')[:8000]}
"""
        return system_prompt, prompt

    def _make_request(self, prompt: str, max_tokens: int = 4000, expect_json: bool = False, system_prompt: str = None) -> Optional[str]:
        """
        Отправка запроса к DeepSeek API

        Args:
            prompt: Промпт для обработки
            max_tokens: Максимальное количество токенов в ответе
            expect_json: Ожидается ли JSON-ответ от API
            system_prompt: Системный промпт (если None, используется базовый)

        Returns:
            Текст ответа или None
        """
        try:
            if not system_prompt:
                system_prompt = 'Ты профессиональный редактор новостей с гибким стилем написания. ' \
                                'Твоя задача - переводить на РУССКИЙ ЯЗЫК, обрабатывать и форматировать новостные статьи для публикации в Telegram ' \
                                'в различных стилях (информативный, ироничный, циничный, шутливый, стебной). ' \
                                'ВЕСЬ РЕЗУЛЬТАТ ДОЛЖЕН БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ! ' \
                                'ВСЕГДА добавляй теги на русском и испанском языках в конце статьи. ' \
                                'НЕ используй символы # для заголовков, только **жирный текст**.'
                            
            if expect_json:
                # Проверяем, нет ли уже инструкции про JSON в конце
                if "В ФОРМАТЕ JSON" not in system_prompt:
                    system_prompt += " Ты ДОЛЖЕН отвечать ИСКЛЮЧИТЕЛЬНО в формате JSON."

            kwargs = {
                'model': 'deepseek-v4-flash',
                'messages': [
                    {
                        'role': 'system',
                        'content': system_prompt
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'max_tokens': max_tokens,
                'temperature': 0.8,
                'stream': False
            }
            if expect_json:
                kwargs['response_format'] = {'type': 'json_object'}
                
            response = self.client.chat.completions.create(**kwargs)

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
            system_prompt, prompt = self._create_rewrite_prompt(article_data, text_length)

            # Делаем запрос - здесь мы не ожидаем JSON, просто текст (так как это команда /rewrite)
            # Для полноты, можно было бы сделать JSON, но rewrite сейчас использует ту же логику
            # Для простоты оставим старый подход только для возврата текста, 
            # но обновим промпт _create_rewrite_prompt
            response = self._make_request(prompt, expect_json=False, system_prompt=system_prompt)

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

    def _create_rewrite_system_prompt(self, style_description: str, length_chars: int, length_name: str) -> str:
        """Создает системный промпт для переписывания статьи с правилами форматирования"""
        return f"""
Ты профессиональный редактор новостного портала. Твоя задача - ПЕРЕПИСАТЬ существующую статью в новом стиле и/или с новой длиной.

СТИЛЬ НАПИСАНИЯ: {style_description}

ОГРАНИЧЕНИЕ ПО ДЛИНЕ:
Длина текста должна быть {length_name.upper()} (примерно {length_chars} символов).
- Если short (1000 символов): краткое изложение основных фактов
- Если medium (2000 символов): стандартная статья с деталями
- Если long (3000 символов): подробная статья с расширенным контекстом

ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:
1. КРИТИЧЕСКИ ВАЖНО: ПЕРЕВЕСТИ ВЕСЬ ТЕКСТ НА РУССКИЙ ЯЗЫК. Весь итоговый результат (заголовок и основной текст) должен быть ИСКЛЮЧИТЕЛЬНО на русском языке, независимо от языка оригинала!
2. Переписать статью в указанном выше стиле
3. Разбить на абзацы для удобного чтения
4. ВАЖНО: НЕ использовать символы форматирования! Никаких *, _, **, __, #, `, ~ и других специальных символов для форматирования!
5. Писать простым текстом без какой-либо разметки
6. НЕ ВКЛЮЧАТЬ информацию об авторе или дате публикации
7. СТРОГО соблюдать ограничение по длине текста (~{length_chars} символов)

СТРУКТУРА ПУБЛИКАЦИИ:
1. ПЕРВАЯ СТРОКА - заголовок статьи (простой текст, без символов форматирования)
2. Пустая строка
3. Основной текст, разбитый на абзацы (длина основного текста ~{length_chars} символов)
4. В конце текста добавить раздел с тегами:

#тег1 #тег2 #тег3 #tag1_es #tag2_es #tag3_es

(Где тег1, тег2, тег3 - это теги на русском языке, а tag1_es, tag2_es, tag3_es - перевод этих же тегов на испанский язык)

ВАЖНО:
- ВЕСЬ ТЕКСТ НОВОСТИ (заголовок и тело) ДОЛЖЕН БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ!
- Используй только простой текст без символов форматирования! Заголовок должен быть на первой строке.
- ОБЯЗАТЕЛЬНО включи теги на русском и испанском в конце текста.
- НЕ забудь про стиль написания: {style_description}!
- СТРОГО соблюдай ограничение по длине: примерно {length_chars} символов для основного текста!
"""

    def _create_rewrite_prompt(self, article_data: Dict[str, str], text_length: str = None) -> tuple[str, str]:
        """
        Создание промпта для переписывания статьи

        Args:
            article_data: Данные статьи
            text_length: Желаемая длина текста

        Returns:
            Системный и пользовательский промпт для API
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

        system_prompt = self._create_rewrite_system_prompt(style_description, length_chars, length_name)

        # Промпт перенесен в system prompt
        prompt = f"""ИСХОДНАЯ СТАТЬЯ:

Заголовок: {article_data.get('title', '')}

Текст:
{article_data.get('text', '')[:8000]}

Перепиши эту статью согласно ВСЕМ указанным требованиям. Результат должен быть готов к публикации в Telegram.
Включая только основной смысл новости (статья могла быть обрезана для экономии места).
"""
        return system_prompt, prompt
