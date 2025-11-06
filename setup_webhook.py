#!/usr/bin/env python3
"""
Утилита для установки и проверки webhook Telegram бота
Использует переменные из .env файла
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')


def check_config():
    """Проверка наличия необходимых переменных"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env")
        return False

    if not WEBHOOK_URL:
        print("❌ Ошибка: WEBHOOK_URL не найден в .env")
        return False

    if not WEBHOOK_URL.startswith('https://'):
        print("❌ Ошибка: WEBHOOK_URL должен начинаться с https://")
        print(f"   Текущее значение: {WEBHOOK_URL}")
        return False

    return True


def get_webhook_info():
    """Получить информацию о текущем webhook"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('ok'):
            info = data.get('result', {})
            return info
        else:
            print(f"❌ Ошибка API: {data.get('description')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return None


def set_webhook():
    """Установить webhook"""
    full_webhook_url = WEBHOOK_URL + WEBHOOK_PATH
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"

    params = {
        'url': full_webhook_url,
        'drop_pending_updates': False
    }

    print(f"\n🔧 Установка webhook...")
    print(f"   URL: {full_webhook_url}")

    try:
        response = requests.post(url, json=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('ok'):
            print(f"✅ Webhook установлен успешно!")
            return True
        else:
            print(f"❌ Ошибка установки: {data.get('description')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return False


def delete_webhook():
    """Удалить webhook"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"

    print(f"\n🗑️  Удаление webhook...")

    try:
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('ok'):
            print(f"✅ Webhook удален успешно!")
            return True
        else:
            print(f"❌ Ошибка удаления: {data.get('description')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return False


def print_webhook_info(info):
    """Вывести информацию о webhook"""
    print("\n📊 Информация о webhook:")
    print(f"   URL: {info.get('url', 'не установлен')}")
    print(f"   Проверка сертификата: {info.get('has_custom_certificate', False)}")
    print(f"   Ожидающих обновлений: {info.get('pending_update_count', 0)}")

    if info.get('last_error_date'):
        from datetime import datetime
        error_date = datetime.fromtimestamp(info['last_error_date'])
        print(f"   ⚠️  Последняя ошибка: {error_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"      Сообщение: {info.get('last_error_message', 'нет')}")

    if info.get('last_synchronization_error_date'):
        from datetime import datetime
        sync_error_date = datetime.fromtimestamp(info['last_synchronization_error_date'])
        print(f"   ⚠️  Ошибка синхронизации: {sync_error_date.strftime('%Y-%m-%d %H:%M:%S')}")

    if info.get('max_connections'):
        print(f"   Макс. соединений: {info['max_connections']}")

    if info.get('allowed_updates'):
        print(f"   Разрешенные обновления: {', '.join(info['allowed_updates'])}")


def main():
    """Главная функция"""
    print("=" * 60)
    print("🤖 Утилита управления Telegram Webhook")
    print("=" * 60)

    # Проверка конфигурации
    if not check_config():
        return 1

    print(f"\n✅ Конфигурация:")
    print(f"   Токен: {TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-10:]}")
    print(f"   Webhook URL: {WEBHOOK_URL}{WEBHOOK_PATH}")

    # Определение действия
    action = sys.argv[1] if len(sys.argv) > 1 else 'info'

    if action == 'set':
        # Установить webhook
        if set_webhook():
            # Показать информацию после установки
            info = get_webhook_info()
            if info:
                print_webhook_info(info)
            return 0
        return 1

    elif action == 'delete' or action == 'remove':
        # Удалить webhook
        if delete_webhook():
            return 0
        return 1

    elif action == 'info' or action == 'status':
        # Показать информацию
        info = get_webhook_info()
        if info:
            print_webhook_info(info)

            # Проверка соответствия URL
            current_url = info.get('url', '')
            expected_url = WEBHOOK_URL + WEBHOOK_PATH

            if current_url and current_url != expected_url:
                print(f"\n⚠️  ВНИМАНИЕ: URL webhook не совпадает с .env!")
                print(f"   Текущий: {current_url}")
                print(f"   Ожидаемый: {expected_url}")
                print(f"\n   Выполните: python setup_webhook.py set")
            elif current_url:
                print(f"\n✅ Webhook настроен корректно!")
            else:
                print(f"\n⚠️  Webhook не установлен!")
                print(f"   Выполните: python setup_webhook.py set")

            return 0
        return 1

    else:
        # Справка
        print("\n📖 Использование:")
        print(f"   python {sys.argv[0]} [action]")
        print("\nДоступные действия:")
        print("   info (default) - показать информацию о webhook")
        print("   status         - то же что и info")
        print("   set            - установить webhook")
        print("   delete         - удалить webhook")
        print("   remove         - то же что и delete")
        print("\nПримеры:")
        print(f"   python {sys.argv[0]} info")
        print(f"   python {sys.argv[0]} set")
        print(f"   python {sys.argv[0]} delete")
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)
