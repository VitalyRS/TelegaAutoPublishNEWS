"""
Утилиты для работы с часовым поясом Мадрида
"""
from datetime import datetime
from zoneinfo import ZoneInfo

# Часовой пояс Мадрида
MADRID_TZ = ZoneInfo("Europe/Madrid")


def now_madrid() -> datetime:
    """
    Получить текущее время в часовом поясе Мадрида

    Returns:
        Текущее время с timezone Мадрида
    """
    return datetime.now(MADRID_TZ)


def to_madrid_tz(dt: datetime) -> datetime:
    """
    Конвертировать datetime в часовой пояс Мадрида

    Args:
        dt: datetime объект (может быть naive или aware)

    Returns:
        datetime с timezone Мадрида
    """
    if dt.tzinfo is None:
        # Если naive datetime, считаем что это UTC
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    return dt.astimezone(MADRID_TZ)


def make_madrid_datetime(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """
    Создать datetime с часовым поясом Мадрида

    Args:
        year: Год
        month: Месяц
        day: День
        hour: Час (по времени Мадрида)
        minute: Минута
        second: Секунда

    Returns:
        datetime с timezone Мадрида
    """
    return datetime(year, month, day, hour, minute, second, tzinfo=MADRID_TZ)
