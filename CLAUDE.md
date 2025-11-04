# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Standard polling mode (recommended for development)
python app.py

# Flask + webhook mode (for production with HTTPS)
python app.py flask
```

## Setup Requirements

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env .env
# Edit .env with your tokens and IDs
```

Required credentials in `.env`:
- `TELEGRAM_BOT_TOKEN` - from @BotFather
- `SOURCE_CHANNEL_ID` - channel to monitor (e.g., @channel or -100123456789)
- `TARGET_CHANNEL_ID` - channel to publish to
- `DEEPSEEK_API_KEY` - from platform.deepseek.com
- `ADMIN_USER_ID` - Telegram user ID for admin commands
- `ARTICLE_STYLE` - writing style (informative, ironic, cynical, playful, mocking) - default: informative

## Technology Stack

- **Telegram Bot Library**: pyTelegramBotAPI (`import telebot`)
- **Scheduler**: APScheduler with BackgroundScheduler for automated publishing
- **Database**: SQLite for news queue management
- **News Parsing**: newspaper3k for article extraction
- **AI Processing**: DeepSeek API via OpenAI library for translation and formatting

## Architecture Overview

This bot implements an automated news pipeline with scheduled publishing:

### Data Flow
1. **telegram_handler.py** monitors SOURCE_CHANNEL_ID for messages containing URLs
   - Only processes messages posted AFTER bot startup (ignores old messages)
   - Filters by `message.date >= bot_start_time`
2. **news_parser.py** extracts article content using newspaper3k
3. **deepseek_client.py** sends articles to DeepSeek API for translation and formatting
4. **scheduler.py** determines publication slot (8:00, 12:00, 16:00, 20:00)
5. **database.py** stores processed articles in SQLite queue
6. **APScheduler** (in app.py) triggers publications at scheduled times
7. **telegram_handler.py** publishes to TARGET_CHANNEL_ID

### Urgent News Bypass
Articles containing keywords from `URGENT_KEYWORDS` (`молния`, `breaking` by default) skip the queue and publish immediately.

### Scheduling Logic
- **One article per slot**: Only 1 news item publishes per time slot
- **Late articles**: News arriving after 20:00 scheduled for next day's 8:00 slot
- **Queue persistence**: SQLite database (`news_queue.db`) stores pending articles across restarts
- **Old message filtering**: Bot ignores channel messages posted before its startup time (`bot_start_time` set in `__init__`)

## Key Module Interactions

### telegram_handler.py ↔ database.py
- `TelegramHandler` uses `NewsDatabase` to:
  - Add processed articles with `add_news()`
  - Retrieve ready-to-publish news with `get_news_for_publication()`
  - Update status with `mark_as_published()` or `mark_as_failed()`

### telegram_handler.py ↔ scheduler.py
- `TelegramHandler` uses `PublicationScheduler` to:
  - Calculate next available slot with `get_next_available_slot(is_urgent)`
  - Check if current time matches publication schedule

### app.py Orchestration
- Sets up BackgroundScheduler (APScheduler) with cron triggers for each hour in `PUBLISH_SCHEDULE`
- Each trigger calls `telegram_handler.publish_scheduled_news()` which:
  - Queries database for articles where `scheduled_time <= now()`
  - Publishes via `publish_news_by_id()`
  - Updates article status
- Bot runs in synchronous mode using `telebot.TeleBot` with polling
- Long-running tasks (URL processing) execute in separate threads to avoid blocking

## Configuration Customization

Edit `.env` to modify:
- `PUBLISH_SCHEDULE=8,12,16,20` - Comma-separated hours (24h format)
- `URGENT_KEYWORDS=молния,breaking` - Keywords for immediate publishing
- `MAX_ARTICLES_PER_RUN=5` - Max articles to process per channel message
- `ARTICLE_STYLE=informative` - Writing style (informative, ironic, cynical, playful, mocking)

## Database Schema

`news_queue` table (news_queue.db):
- `scheduled_time` - When article will publish
- `status` - `pending`, `published`, or `failed`
- `is_urgent` - Boolean flag for immediate publication
- URL uniqueness constraint prevents duplicate processing

## Bot Commands

Admin-only commands (require `ADMIN_USER_ID` match):
- `/publish_now <id>` - Force immediate publication of queued article
- `/clear_queue` - Remove all pending articles
- `/set_style <style>` - Change article writing style (informative, ironic, cynical, playful, mocking)

Public commands:
- `/status` - Queue statistics and next publication time
- `/queue` - List all pending articles
- `/get_style` - Show current writing style

## DeepSeek Prompt Structure

`deepseek_client.py` sends articles with system prompt defining output format:
- Translate to Russian
- News style formatting in selected style (informative, ironic, cynical, playful, mocking)
- Telegram Markdown (`**bold**`, `*italic*`, lists) - NO # symbols for headers
- Paragraph structure with subheadings (using **bold** instead of #)
- Tags in Russian and Spanish at the end of article
- NO author or publication date information

Article structure:
1. Title (in **bold**, not with #)
2. Main text with subheadings
3. Tags section with Russian and Spanish hashtags
4. Source link (added automatically in telegram_handler.py)

The processed text is stored in database and published with source link footer.

## Writing Styles

The bot supports multiple writing styles that can be changed dynamically:

- **informative** (default): Neutral, factual news style with objective reporting
- **ironic**: Subtle irony and hints throughout the article
- **cynical**: Skeptical and critical perspective on events
- **playful**: Light humor and playful phrasing
- **mocking**: Satirical and biting sarcasm

Change style using `/set_style <style>` command (admin only). The style applies to all new articles processed after the change. The DeepSeekClient maintains a single instance throughout the bot's lifetime, allowing dynamic style switching without restart.

## Implementation Details

### Telegram Handler
- Uses decorator-based handlers: `@bot.channel_post_handler()` for channel messages
- Commands registered via `@bot.message_handler(commands=['...'])`
- `infinity_polling()` for continuous message polling
- Message handlers execute synchronously; background tasks use threading
- All handlers are set up in `_setup_handlers()` during initialization

### Message Processing Flow
1. Channel post received → `_handle_channel_message()`
2. URLs extracted → spawns thread for `_process_urls()`
3. Thread parses articles, processes via DeepSeek, adds to database
4. Urgent news published immediately via `publish_news_by_id()`
5. Regular news waits for APScheduler to trigger `publish_scheduled_news()`

## Troubleshooting

Check `bot.log` for errors. Common issues:
- **Channel access**: Bot must be admin in both SOURCE and TARGET channels
- **newspaper3k parsing**: Some sites block automated scraping
- **Schedule not triggering**: Verify BackgroundScheduler is running and time slots are future times
- **Import errors**: Ensure `pyTelegramBotAPI` (not `python-telegram-bot`) is installed
- **Polling errors**: Check bot token validity and network connectivity
