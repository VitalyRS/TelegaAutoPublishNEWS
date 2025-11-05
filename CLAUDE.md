# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Polling mode (recommended for development and simple setups)
python app.py

# Webhook mode (recommended for production with HTTPS)
python app.py webhook
```

### Polling vs Webhook

**Polling Mode (default)**:
- Bot continuously polls Telegram servers for updates
- Easy to set up, no HTTPS required
- Works behind NAT/firewall
- Suitable for development and small deployments
- Command: `python app.py`

**Webhook Mode**:
- Telegram sends updates directly to your server
- Requires HTTPS with valid SSL certificate
- More efficient for high-load scenarios
- Requires public IP or domain
- Lower latency for message processing
- Command: `python app.py webhook`

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
- `DATABASE_URL` - PostgreSQL connection URL (recommended for Aiven) OR separate DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD parameters

### Webhook Setup (Optional, for Production)

For webhook mode, you also need:

```bash
# In .env file
WEBHOOK_URL=https://your-domain.com
WEBHOOK_PATH=/webhook
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

**Requirements for webhook mode:**
1. **HTTPS domain** with valid SSL certificate (Telegram requires HTTPS)
2. **Public IP** or domain accessible from the internet
3. **Port configuration**: Telegram supports ports 443, 80, 88, 8443
4. **Reverse proxy** (nginx/Apache) recommended for SSL termination

**Example nginx configuration:**
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:5000/webhook;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Testing webhook:**
```bash
# Start bot in webhook mode
python app.py webhook

# Check webhook status
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

## Technology Stack

- **Telegram Bot Library**: pyTelegramBotAPI (`import telebot`)
- **Scheduler**: APScheduler with BackgroundScheduler for automated publishing
- **Database**: PostgreSQL (via Aiven or self-hosted) for news queue management
  - Uses psycopg2 driver with connection pooling for optimal performance
  - Supports both DATABASE_URL and separate connection parameters
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
5. **database.py** stores processed articles in PostgreSQL queue
6. **APScheduler** (in app.py) triggers publications at scheduled times
7. **telegram_handler.py** publishes to TARGET_CHANNEL_ID

### Urgent News Bypass
Articles containing keywords from `URGENT_KEYWORDS` (`молния`, `breaking` by default) skip the queue and publish immediately.

### Scheduling Logic
- **One article per slot**: Only 1 news item publishes per time slot
- **Late articles**: News arriving after 20:00 scheduled for next day's 8:00 slot
- **Queue persistence**: PostgreSQL database stores pending articles across restarts with full ACID compliance
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
- Initializes PostgreSQL database and loads configuration from `bot_config` table
- Sets up BackgroundScheduler (APScheduler) with cron triggers for:
  - **Publication tasks**: Each hour in `PUBLISH_SCHEDULE` (default: 8, 12, 16, 20)
  - **Cleanup task**: Daily at 3:00 AM to delete published articles older than 7 days
- Each publication trigger calls `telegram_handler.publish_scheduled_news()` which:
  - Queries database for articles where `scheduled_time <= now()`
  - Publishes via `publish_news_by_id()`
  - Updates article status
- Bot supports two modes: polling (default, `infinity_polling()`) and webhook (production, Flask route)
- Long-running tasks (URL processing) execute in separate threads to avoid blocking
- In webhook mode, Flask server handles incoming updates via POST requests to WEBHOOK_PATH

## Configuration Customization

**Configuration is now stored in PostgreSQL database** with fallback to `.env` variables. This allows runtime configuration changes without restarting the bot.

### Configuration Priority
1. **Database settings** (highest priority) - stored in `bot_config` table
2. **Environment variables** (.env file) - used as defaults on first run

### Configurable Settings (stored in database)
- `PUBLISH_SCHEDULE=8,12,16,20` - Comma-separated hours (24h format)
- `URGENT_KEYWORDS=молния,breaking` - Keywords for immediate publishing
- `MAX_ARTICLES_PER_RUN=5` - Max articles to process per channel message
- `ARTICLE_STYLE=informative` - Writing style (informative, ironic, cynical, playful, mocking)
- `CHECK_INTERVAL=60` - Interval for background checks (seconds)

### Managing Configuration
- Use `/config` to view current settings from database
- Use `/set_config <key> <value>` to update settings (admin only)
- Use `/reload_config` to reload settings without restart (admin only)
- Changes to `PUBLISH_SCHEDULE` require bot restart to update APScheduler

### Security Notes
- **Tokens and API keys** (TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY) remain in `.env` for security
- **Database credentials** also remain in `.env`

## Database Configuration

### Aiven PostgreSQL Setup (Recommended)

The bot uses **Aiven for PostgreSQL** as the cloud database service. To configure:

1. Create PostgreSQL service on [Aiven Console](https://console.aiven.io/)
2. Copy the Service URI from Aiven dashboard
3. Add to `.env` file:
   ```
   DATABASE_URL=postgresql://user:password@host:port/defaultdb?sslmode=require
   ```

**Alternative**: Use separate parameters if DATABASE_URL is not available:
```
DB_HOST=your-aiven-host.aivencloud.com
DB_PORT=12345
DB_NAME=defaultdb
DB_USER=avnadmin
DB_PASSWORD=your_password
DB_SSLMODE=require
```

### Database Schema

#### `news_queue` table (PostgreSQL):
Stores articles pending publication or already published.

- `id` - SERIAL PRIMARY KEY (auto-incrementing)
- `url` - TEXT UNIQUE NOT NULL (prevents duplicate processing)
- `title` - TEXT
- `original_text` - TEXT
- `processed_text` - TEXT
- `scheduled_time` - TIMESTAMP (when article will publish)
- `status` - TEXT DEFAULT 'pending' (pending/published/failed)
- `is_urgent` - BOOLEAN DEFAULT FALSE (immediate publication flag)
- `created_at` - TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `published_at` - TIMESTAMP

**Indexes** for performance:
- `idx_status` on (status)
- `idx_scheduled_time` on (scheduled_time)
- `idx_is_urgent` on (is_urgent)
- `idx_status_scheduled` composite on (status, scheduled_time)
- `idx_published_at` on (published_at) - for cleanup queries

**Automatic Cleanup**: Published articles older than 7 days are automatically deleted daily at 3:00 AM to keep database size manageable.

#### `bot_config` table (PostgreSQL):
Stores bot configuration settings for runtime customization.

- `key` - TEXT PRIMARY KEY (setting name)
- `value` - TEXT NOT NULL (setting value)
- `updated_at` - TIMESTAMP DEFAULT CURRENT_TIMESTAMP (last update time)

**Default settings** initialized automatically:
- PUBLISH_SCHEDULE=8,12,16,20
- URGENT_KEYWORDS=молния,breaking
- MAX_ARTICLES_PER_RUN=5
- ARTICLE_STYLE=informative
- CHECK_INTERVAL=60

### Database Connection

The `NewsDatabase` class uses connection pooling (1-10 connections) for optimal performance:
- Automatic connection management with context managers
- Transaction rollback on errors
- SSL/TLS support for secure connections (required for Aiven)
- Graceful connection cleanup on shutdown

## Bot Commands

### Admin-only commands (require `ADMIN_USER_ID` match):

**Article Management:**
- `/publish_now <id>` - Force immediate publication of queued article
- `/clear_queue` - Remove all pending articles
- `/view <id>` - Preview article by ID before publication
- `/rewrite <id>` - Rewrite article with new style and/or text length
  - Opens interactive menu to select new style and/or length
  - Rewrites the article through DeepSeek API with selected parameters
  - Updates the article in database with rewritten text
  - Useful when you want to change how an article is written without re-parsing from source
  - Example workflow: `/rewrite 123` → select "ironic" style → confirm → article is rewritten

**Configuration Management:**
- `/config` - Show all bot configuration settings from database
- `/set_config <key> <value>` - Update configuration setting in database
  - Example: `/set_config ARTICLE_STYLE ironic`
  - Example: `/set_config PUBLISH_SCHEDULE 6,10,14,18,22`
- `/reload_config` - Reload configuration from database without restart
- `/set_style <style>` - Change article writing style (shortcut for `/set_config ARTICLE_STYLE`)
  - Available styles: informative, ironic, cynical, playful, mocking

### Public commands:
- `/status` - Queue statistics and next publication time
- `/queue` - List all pending articles with scheduled times
- `/get_style` - Show current writing style

## DeepSeek Prompt Structure

`deepseek_client.py` sends articles with system prompt defining output format:
- Translate to Russian
- News style formatting in selected style (informative, ironic, cynical, playful, mocking)
- Text length control (short: ~1000 chars, medium: ~2000 chars, long: ~3000 chars)
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

### Article Rewriting

The `DeepSeekClient.rewrite_article()` method allows rewriting existing articles with different parameters:
- **Purpose**: Change style or length of already processed articles without re-parsing the source
- **Parameters**:
  - `new_style`: Optional - change writing style (informative, ironic, cynical, playful, mocking)
  - `text_length`: Optional - change article length (short, medium, long)
- **Usage**: Accessed via `/rewrite <id>` command through interactive menu
- **Implementation**: Uses original article text from database, applies new prompt with specified parameters
- **Preserves**: Original URL, title, and source text remain unchanged

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
- **Polling mode**: `infinity_polling()` for continuous message polling (default)
- **Webhook mode**: `set_webhook()` configures Telegram to send updates to Flask route
- Message handlers execute synchronously; background tasks use threading
- All handlers are set up in `_setup_handlers()` during initialization
- In webhook mode, `process_webhook_update()` handles incoming POST requests from Telegram

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
- **Webhook errors**:
  - Verify WEBHOOK_URL is HTTPS (Telegram requires SSL)
  - Check webhook status: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
  - Ensure Flask is accessible from the internet on configured port
  - Verify reverse proxy (nginx/Apache) is properly configured
  - Check firewall allows incoming connections to webhook port
  - Telegram only supports ports: 443, 80, 88, 8443
- **Database connection**:
  - Verify DATABASE_URL or DB_* parameters are correctly set
  - Check SSL/TLS settings (Aiven requires `sslmode=require`)
  - Ensure PostgreSQL service is running and accessible
  - Check firewall rules and network connectivity to database host
  - Verify credentials (username/password) are correct
