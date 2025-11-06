# Развертывание бота на Railway.com

Это руководство описывает процесс развертывания Telegram бота для автоматической публикации новостей на платформе Railway.com.

## Подготовленные файлы для развертывания

В проекте уже созданы все необходимые файлы:

1. **Procfile** - команда запуска бота в webhook режиме
   ```
   web: python app.py webhook
   ```

2. **requirements.txt** - все Python зависимости

3. **runtime.txt** - версия Python (3.11.9)

4. **.env.example** - пример конфигурации с переменными окружения

## Пошаговая инструкция по развертыванию

### 1. Создание проекта на Railway

1. Перейдите на [Railway.com](https://railway.com/)
2. Зарегистрируйтесь или войдите в аккаунт
3. Нажмите **New Project**
4. Выберите **Deploy from GitHub repo**
5. Выберите ваш репозиторий с ботом
6. Railway автоматически определит Python приложение и начнет сборку

### 2. Настройка PostgreSQL базы данных

Railway предоставляет встроенный PostgreSQL:

1. В проекте нажмите **New** → **Database** → **Add PostgreSQL**
2. Railway автоматически создаст переменную `DATABASE_URL`
3. Эта переменная будет доступна вашему приложению автоматически

### 3. Настройка переменных окружения

В разделе **Variables** вашего проекта добавьте следующие переменные:

#### Обязательные переменные:

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # от @BotFather
SOURCE_CHANNEL_ID=@your_source_channel
TARGET_CHANNEL_ID=@your_target_channel

# DeepSeek API
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx  # от platform.deepseek.com

# Admin User
ADMIN_USER_ID=123456789  # ваш Telegram user ID

# Webhook Configuration
WEBHOOK_URL=https://your-app-name.up.railway.app  # URL вашего Railway приложения
WEBHOOK_PATH=/webhook
FLASK_HOST=0.0.0.0
# Примечание: Railway автоматически устанавливает переменную PORT, не нужно указывать вручную
```

#### Опциональные переменные (есть значения по умолчанию):

```bash
PUBLISH_SCHEDULE=8,12,16,20
URGENT_KEYWORDS=молния,breaking
ARTICLE_STYLE=informative
MAX_ARTICLES_PER_RUN=5
CHECK_INTERVAL=60
```

**Важно**: `DATABASE_URL` будет создана автоматически при добавлении PostgreSQL базы.

### 4. Настройка домена и HTTPS

Railway автоматически предоставляет:
- HTTPS домен вида: `https://your-app-name.up.railway.app`
- SSL сертификат (обязательно для Telegram webhook)

**Получение URL вашего приложения:**
1. Откройте Settings → Networking
2. Скопируйте URL в формате: `https://your-app-name.up.railway.app`
3. Используйте этот URL для переменной `WEBHOOK_URL`

### 5. Проверка развертывания

После настройки всех переменных:

1. **Проверьте логи**:
   - Откройте раздел **Deployments**
   - Выберите последний деплой
   - Проверьте логи на наличие ошибок

2. **Проверьте webhook**:
   - В Telegram боте используйте команду `/webhook_info`
   - Убедитесь, что webhook установлен корректно

3. **Проверьте здоровье приложения**:
   - Откройте `https://your-app-name.up.railway.app/health`
   - Должно вернуть: `OK`

### 6. Настройка бота как администратора каналов

Не забудьте:
1. Добавить бота в SOURCE_CHANNEL_ID как администратора с правами чтения
2. Добавить бота в TARGET_CHANNEL_ID как администратора с правами публикации

## Управление ботом после развертывания

### Команды администратора

Доступны в Telegram после развертывания:

- `/status` - статистика очереди и время следующей публикации
- `/queue` - список всех ожидающих статей
- `/publish_now <id>` - немедленная публикация статьи
- `/view <id>` - предпросмотр статьи
- `/rewrite <id>` - переписать статью с новым стилем
- `/config` - показать настройки бота
- `/set_config <key> <value>` - изменить настройку
- `/set_style <style>` - изменить стиль написания
- `/webhook_info` - информация о webhook
- `/clear_queue` - очистить очередь
- `/reload_config` - перезагрузить конфигурацию

### Мониторинг

Railway предоставляет:
- **Metrics** - использование CPU, памяти, сети
- **Logs** - логи приложения в реальном времени
- **Health checks** - автоматическая проверка доступности

### Обновление кода

После push в GitHub:
1. Railway автоматически начнет новый деплой
2. Приложение будет пересобрано с новым кодом
3. Старая версия будет заменена новой без простоев

## Расчет стоимости

Railway предоставляет:
- **Hobby план**: $5/месяц за проект + ресурсы
- **$5 бесплатно** каждый месяц для новых пользователей
- PostgreSQL база включена в стоимость

**Примерное потребление для этого бота:**
- ~0.1-0.5 vCPU
- ~100-300 MB RAM
- ~1-5 GB сетевого трафика

## Troubleshooting

### Проблема: Webhook не работает

**Решение:**
1. Проверьте, что `WEBHOOK_URL` содержит правильный HTTPS URL
2. Проверьте логи Railway на наличие ошибок Flask
3. Используйте `/webhook_info` для диагностики
4. Убедитесь, что приложение запущено и отвечает на `/health`

### Проблема: База данных не подключается

**Решение:**
1. Проверьте, что PostgreSQL база добавлена в проект
2. Проверьте наличие переменной `DATABASE_URL` в Variables
3. Проверьте логи на ошибки подключения к БД

### Проблема: Бот не отвечает на команды

**Решение:**
1. Проверьте, что `ADMIN_USER_ID` указан корректно
2. Убедитесь, что бот добавлен в каналы как администратор
3. Проверьте логи на ошибки обработки команд

### Проблема: Деплой падает с ошибкой

**Решение:**
1. Проверьте логи сборки в Railway
2. Убедитесь, что все зависимости в `requirements.txt` актуальны
3. Проверьте, что `runtime.txt` содержит поддерживаемую версию Python

## Полезные ссылки

- [Railway Documentation](https://docs.railway.app/)
- [Railway Python Guide](https://docs.railway.app/guides/python)
- [Telegram Bot API - Webhooks](https://core.telegram.org/bots/api#setwebhook)
- [DeepSeek API Documentation](https://platform.deepseek.com/api-docs/)

## Поддержка

При возникновении проблем:
1. Проверьте логи в Railway Dashboard
2. Проверьте файл `bot.log` в Deployments
3. Используйте команду `/webhook_info` в Telegram для диагностики webhook
4. Обратитесь к документации Railway и Telegram Bot API
