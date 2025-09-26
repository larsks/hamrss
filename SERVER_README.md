# Ham Radio Scraper Server

A configurable server that periodically scrapes ham radio equipment catalogs from multiple sources and stores the data in PostgreSQL.

## Features

- **Configurable Drivers**: Supports multiple catalog sources (HRO, MTC Radio, R&L Electronics)
- **Scheduled Scraping**: Configurable intervals for automatic data collection
- **PostgreSQL Storage**: Robust database schema with product tracking and deduplication
- **Environment Configuration**: All settings via environment variables using pydantic-settings
- **Concurrent Processing**: Configurable concurrent driver execution with timeouts
- **Error Handling**: Comprehensive error logging and recovery
- **Health Monitoring**: Built-in health checks and scraping statistics

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Setup PostgreSQL Database

```sql
CREATE DATABASE hamrss;
CREATE USER hamrss WITH PASSWORD 'hamrss';
GRANT ALL PRIVILEGES ON DATABASE hamrss TO hamrss;
```

### 3. Configure Environment

Copy `.env.example` to `.env` and adjust settings:

```bash
cp .env.example .env
# Edit .env with your database connection and preferences
```

### 4. Run Component Tests

```bash
uv run python test_server.py     # Test imports and configuration
uv run python test_scraper_logic.py  # Test driver logic
```

### 5. Start the Server

```bash
uv run hamrss-server
```

### 6. Stopping the Server

To gracefully stop the server, use **Ctrl+C** (SIGINT). The server will:
- Stop accepting new scraping jobs
- Complete any running scrapes
- Clean up database connections
- Exit gracefully

```bash
# Start server
uv run hamrss-server

# ... server runs ...

# Stop with Ctrl+C
^C
Shutdown requested by user
```

## Configuration

All configuration is done via environment variables with the `HAMRSS_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `HAMRSS_DATABASE_URL` | `postgresql+psycopg://hamrss:hamrss@localhost/hamrss` | PostgreSQL connection URL |
| `HAMRSS_SCRAPE_INTERVAL_HOURS` | `6` | Hours between scraping cycles |
| `HAMRSS_ENABLED_DRIVERS` | `hamrss.driver.hro,hamrss.driver.mtc,hamrss.driver.rlelectronics` | Comma-separated driver list |
| `HAMRSS_PLAYWRIGHT_SERVER_URL` | `ws://127.0.0.1:3000/` | Playwright server URL (for HRO driver) |
| `HAMRSS_LOG_LEVEL` | `INFO` | Logging level |
| `HAMRSS_MAX_CONCURRENT_DRIVERS` | `3` | Max concurrent driver processes |
| `HAMRSS_SCRAPE_TIMEOUT_MINUTES` | `30` | Timeout per driver |

## Database Schema

The server creates these tables automatically:

- **`products`**: Scraped product data with deduplication and lifecycle tracking
- **`scrape_runs`**: High-level scraping session tracking
- **`driver_stats`**: Per-driver/category performance statistics
- **`scrape_errors`**: Detailed error logging

## Driver Architecture

### Existing Drivers

1. **HRO (Ham Radio Outlet)**: Requires Playwright for dynamic content
2. **MTC Radio**: Uses requests for simple HTTP scraping
3. **R&L Electronics**: Uses requests for table-based data

### Driver Requirements

All drivers must implement the `Catalog` protocol:

```python
class Catalog(Protocol):
    def get_categories(self) -> list[str]: ...
    def get_items(self, category_name: str): ...
```

## Server Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Scheduler     │────│  Orchestrator    │────│  DriverScraper  │
│ (APScheduler)   │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                       ┌──────────────────┐
                       │  StorageManager  │
                       │                  │
                       └──────────────────┘
                                │
                       ┌──────────────────┐
                       │   PostgreSQL     │
                       │                  │
                       └──────────────────┘
```

### Components

- **Scheduler**: Manages periodic execution using APScheduler
- **Orchestrator**: Coordinates driver execution and error handling
- **DriverScraper**: Loads and executes individual catalog drivers
- **StorageManager**: Handles database operations and deduplication

## Data Flow

1. **Scheduled Trigger**: APScheduler triggers scraping cycle
2. **Driver Loading**: Load configured drivers dynamically
3. **Concurrent Execution**: Run drivers in parallel with concurrency limits
4. **Data Processing**: Extract, transform, and deduplicate product data
5. **Database Storage**: Store products with lifecycle tracking
6. **Statistics**: Record performance metrics and error details

## Monitoring

### Health Checks

The server tracks:
- Database connectivity
- Recent scrape run status
- Product counts by driver/category
- Error rates and types

### Logging

Structured logging includes:
- Scrape cycle start/completion
- Per-driver statistics
- Error details with stack traces
- Database operation metrics

### Database Queries

Common monitoring queries:

```sql
-- Recent scrape runs
SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 10;

-- Product counts by source
SELECT driver_name, category, COUNT(*) as count
FROM products WHERE is_active = true
GROUP BY driver_name, category;

-- Error summary
SELECT driver_name, error_type, COUNT(*) as count
FROM scrape_errors
WHERE occurred_at > NOW() - INTERVAL '24 hours'
GROUP BY driver_name, error_type;
```

## Production Deployment

### Playwright Server (for HRO driver)

Start a Playwright server for the HRO driver:

```bash
npx playwright install
npx playwright run-server --port 3000 --host 0.0.0.0
```

### Process Management

Use systemd, supervisor, or Docker to manage the server process:

```ini
# /etc/systemd/system/hamrss-server.service
[Unit]
Description=Ham Radio Scraper Server
After=network.target postgresql.service

[Service]
Type=simple
User=hamrss
WorkingDirectory=/opt/hamrss
Environment=HAMRSS_DATABASE_URL=postgresql+psycopg://hamrss:password@localhost/hamrss
ExecStart=/opt/hamrss/.venv/bin/hamrss-server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Database Backup

Regular backups are recommended:

```bash
pg_dump hamrss > hamrss_backup_$(date +%Y%m%d).sql
```

## Troubleshooting

### Common Issues

1. **Database Connection**: Check PostgreSQL is running and credentials are correct
2. **Playwright Timeout**: Ensure Playwright server is accessible if using HRO driver
3. **Driver Errors**: Check individual driver logs and network connectivity
4. **Memory Usage**: Monitor memory usage with high product volumes

### Debug Mode

Enable debug logging:

```bash
export HAMRSS_LOG_LEVEL=DEBUG
uv run hamrss-server
```

## Development

### Adding New Drivers

1. Create driver module in `hamrss/driver/`
2. Implement `Catalog` protocol
3. Add to `HAMRSS_ENABLED_DRIVERS` configuration
4. Test with component tests

### Testing

```bash
# Component tests (no database required)
uv run python test_server.py
uv run python test_scraper_logic.py

# Integration tests (requires database)
uv run hamrss-server
```

## License

This project follows the same license as the main hamrss package.
