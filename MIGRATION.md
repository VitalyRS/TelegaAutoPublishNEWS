# Migration Guide: SQLite to PostgreSQL

This guide explains how to migrate from the old SQLite database to the new PostgreSQL (Aiven) setup.

## Why PostgreSQL?

The bot has been upgraded to use PostgreSQL instead of SQLite for the following benefits:

- **Cloud-hosted**: Aiven provides managed PostgreSQL with automatic backups and high availability
- **Reliability**: Full ACID compliance and better concurrent access handling
- **Scalability**: Better performance for larger datasets and multiple connections
- **No local files**: Database persists independently of the bot instance
- **Production-ready**: SSL/TLS encryption and enterprise-grade security

## Prerequisites

Before migrating, ensure you have:

1. **Aiven PostgreSQL service** set up:
   - Create account at [Aiven Console](https://console.aiven.io/)
   - Create a PostgreSQL service
   - Note down the Service URI from the dashboard

2. **Updated dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment configured**: Add to your `.env` file:
   ```bash
   DATABASE_URL=postgresql://user:password@host:port/defaultdb?sslmode=require
   ```

   Or use separate parameters:
   ```bash
   DB_HOST=your-aiven-host.aivencloud.com
   DB_PORT=12345
   DB_NAME=defaultdb
   DB_USER=avnadmin
   DB_PASSWORD=your_password
   DB_SSLMODE=require
   ```

## Migration Steps

### Step 1: Backup Your SQLite Database

Before migrating, create a backup of your existing database:

```bash
cp news_queue.db news_queue.db.backup
```

### Step 2: Configure PostgreSQL Connection

Add your PostgreSQL credentials to `.env` file as shown in Prerequisites.

### Step 3: Test PostgreSQL Connection

Verify the connection works:

```bash
python -c "from database import NewsDatabase; db = NewsDatabase(); print('Connection successful!'); db.close()"
```

If you see "Connection successful!", proceed to the next step.

### Step 4: Run Migration Script

Execute the migration script to transfer data from SQLite to PostgreSQL:

```bash
python migrate_to_postgres.py
```

Or specify a custom SQLite path:

```bash
python migrate_to_postgres.py /path/to/news_queue.db
```

The script will:
- Read all records from SQLite database
- Insert them into PostgreSQL (skipping duplicates)
- Update the auto-increment sequence
- Report statistics (success, skipped, errors)

### Step 5: Verify Migration

Check that your data was migrated successfully:

```bash
python -c "
from database import NewsDatabase
db = NewsDatabase()
stats = db.get_queue_status()
print(f'Total records: {stats[\"total\"]}')
print(f'Pending: {stats[\"pending\"]}')
print(f'Published: {stats[\"published\"]}')
db.close()
"
```

### Step 6: Start the Bot

Once migration is complete, start the bot normally:

```bash
python app.py
```

The bot will now use PostgreSQL for all database operations.

## Troubleshooting

### Connection Errors

**Error**: `could not connect to server`

**Solution**: Check your firewall rules and ensure the PostgreSQL host is accessible. Aiven services may require whitelisting your IP address.

### SSL/TLS Errors

**Error**: `SSL connection required`

**Solution**: Ensure `DB_SSLMODE=require` is set in your `.env` file (mandatory for Aiven).

### Authentication Errors

**Error**: `password authentication failed`

**Solution**: Double-check your credentials. Aiven usernames are usually `avnadmin`, and passwords can be reset in the console.

### Migration Duplicates

If you run the migration script multiple times, duplicate entries will be skipped automatically (URL is a unique constraint).

### Sequence Issues

If new records fail to insert after migration with "duplicate key" errors, manually reset the sequence:

```sql
SELECT setval('news_queue_id_seq', (SELECT MAX(id) FROM news_queue));
```

## Rollback (if needed)

If you need to rollback to SQLite:

1. Stop the bot
2. Remove PostgreSQL configuration from `.env`
3. Restore the backup: `cp news_queue.db.backup news_queue.db`
4. Revert code changes using git: `git checkout main -- database.py requirements.txt`
5. Reinstall old dependencies: `pip install -r requirements.txt`

## Database Schema Changes

The PostgreSQL schema is equivalent to the old SQLite schema with these improvements:

| Old (SQLite) | New (PostgreSQL) |
|--------------|------------------|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` |
| `is_urgent INTEGER DEFAULT 0` | `is_urgent BOOLEAN DEFAULT FALSE` |
| Query parameters: `?` | Query parameters: `%s` |
| No connection pooling | Connection pool (1-10 connections) |

All application logic remains the same - only the database layer has changed.

## Additional Resources

- [Aiven PostgreSQL Documentation](https://docs.aiven.io/docs/products/postgresql)
- [psycopg2 Documentation](https://www.psycopg.org/docs/)
- [PostgreSQL Official Docs](https://www.postgresql.org/docs/)

## Support

If you encounter issues during migration, check:
1. Bot logs: `tail -f bot.log`
2. PostgreSQL connection string format
3. Network connectivity to Aiven service
4. Credentials and permissions

For further assistance, please open an issue on the repository.
