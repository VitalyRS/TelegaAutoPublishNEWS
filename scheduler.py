"""
Планировщик публикаций новостей
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from config import Config
from timezone_utils import now_madrid, MADRID_TZ

logger = logging.getLogger(__name__)


class PublicationScheduler:
    """Класс для определения времени публикации новостей"""

    @property
    def publish_hours(self):
        """Получить часы публикации динамически из Config"""
        return Config.get_publish_hours()

    def get_next_available_slot(self, is_urgent: bool = False, db=None) -> datetime:
        """
        Получить следующий доступный слот для публикации

        Args:
            is_urgent: Срочная новость (публикуется немедленно)
            db: Объект базы данных для проверки занятости слотов

        Returns:
            Время публикации (с timezone Мадрида)
        """
        if is_urgent:
            # Срочные новости публикуются немедленно
            return now_madrid()

        now = now_madrid()
        current_date = now.date()
        current_hour = now.hour

        # Создаем список всех доступных слотов (сегодня + следующие дни)
        available_slots = []

        # Добавляем слоты на сегодня (если еще не прошли)
        for hour in sorted(self.publish_hours):
            if hour > current_hour:
                slot_time = datetime.combine(current_date, datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)
                available_slots.append(slot_time)

        # Добавляем слоты на следующие 7 дней
        for day_offset in range(1, 8):
            next_date = current_date + timedelta(days=day_offset)
            for hour in sorted(self.publish_hours):
                slot_time = datetime.combine(next_date, datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)
                available_slots.append(slot_time)

        # Если база данных передана, ищем первый свободный слот
        if db:
            for slot_time in available_slots:
                news_count = db.get_next_slot_news_count(slot_time)
                if news_count == 0:
                    logger.info(f"Найден свободный слот: {slot_time}")
                    return slot_time

            # Если все слоты заняты, возвращаем последний слот (через 7 дней)
            logger.warning(f"Все слоты заняты на 7 дней вперед. Используем последний слот: {available_slots[-1]}")
            return available_slots[-1]
        else:
            # Если база данных не передана, возвращаем первый доступный слот по времени
            slot_time = available_slots[0] if available_slots else now_madrid()
            logger.info(f"База данных не передана. Используем первый слот: {slot_time}")
            return slot_time

    def get_specific_slot(self, target_date: datetime, slot_index: int = 0) -> Optional[datetime]:
        """
        Получить конкретный слот на определенную дату

        Args:
            target_date: Целевая дата
            slot_index: Индекс слота (0 = первый слот дня)

        Returns:
            Время слота или None (с timezone Мадрида)
        """
        if slot_index >= len(self.publish_hours):
            logger.warning(f"Неверный индекс слота: {slot_index}")
            return None

        hour = sorted(self.publish_hours)[slot_index]
        slot_time = datetime.combine(target_date.date(), datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)

        return slot_time

    def get_all_slots_for_date(self, target_date: datetime) -> list:
        """
        Получить все слоты для определенной даты

        Args:
            target_date: Целевая дата

        Returns:
            Список времен слотов (с timezone Мадрида)
        """
        slots = []
        for hour in sorted(self.publish_hours):
            slot_time = datetime.combine(target_date.date(), datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)
            slots.append(slot_time)

        return slots

    def is_publication_time(self, check_time: Optional[datetime] = None) -> bool:
        """
        Проверить, является ли текущее время временем публикации

        Args:
            check_time: Время для проверки (если None - текущее время Мадрида)

        Returns:
            True если время публикации
        """
        if check_time is None:
            check_time = now_madrid()

        current_hour = check_time.hour
        current_minute = check_time.minute

        # Проверяем, что сейчас один из часов публикации и первые 5 минут
        if current_hour in self.publish_hours and current_minute < 5:
            return True

        return False

    def calculate_slot_for_news(self, news_count: int, current_slot_news: int = 0) -> datetime:
        """
        Рассчитать слот для новости с учетом текущей загрузки

        Args:
            news_count: Порядковый номер новости
            current_slot_news: Количество новостей уже в текущем слоте

        Returns:
            Время публикации (с timezone Мадрида)
        """
        now = now_madrid()
        current_date = now.date()
        current_hour = now.hour

        # Находим ближайший доступный слот
        available_slots = []

        # Слоты на сегодня (если еще не прошли)
        for hour in sorted(self.publish_hours):
            if hour > current_hour:
                slot_time = datetime.combine(current_date, datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)
                available_slots.append(slot_time)

        # Если слотов на сегодня не хватает, добавляем слоты на следующие дни
        days_ahead = 1
        while len(available_slots) < news_count + current_slot_news:
            next_date = current_date + timedelta(days=days_ahead)
            for hour in sorted(self.publish_hours):
                slot_time = datetime.combine(next_date, datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)
                available_slots.append(slot_time)
            days_ahead += 1

        # Возвращаем слот с учетом уже занятых
        slot_index = current_slot_news + news_count - 1
        if slot_index < len(available_slots):
            return available_slots[slot_index]

        return available_slots[-1]

    def get_next_publication_time(self) -> datetime:
        """
        Получить время следующей публикации

        Returns:
            Время следующей публикации (с timezone Мадрида)
        """
        now = now_madrid()
        next_slots = []

        # Проверяем оставшиеся слоты сегодня
        for hour in sorted(self.publish_hours):
            slot_time = datetime.combine(now.date(), datetime.min.time().replace(hour=hour), tzinfo=MADRID_TZ)
            if slot_time > now:
                next_slots.append(slot_time)

        if next_slots:
            return min(next_slots)

        # Если слотов на сегодня нет, возвращаем первый слот завтра
        tomorrow = now.date() + timedelta(days=1)
        first_hour = min(self.publish_hours)
        return datetime.combine(tomorrow, datetime.min.time().replace(hour=first_hour), tzinfo=MADRID_TZ)

    def format_schedule(self) -> str:
        """
        Отформатировать расписание для отображения

        Returns:
            Строка с расписанием
        """
        hours_str = ", ".join([f"{h:02d}:00" for h in sorted(self.publish_hours)])
        return f"Расписание публикаций: {hours_str}"
