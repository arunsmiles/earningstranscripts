# Earnings Transcript Scheduler

Automate earnings transcript and SEC filing downloads with a production-ready scheduling system featuring dynamic job queues and persistent storage.

## Features

- ✅ **Dynamic Job Management** - Add, remove, and modify jobs at runtime
- ✅ **Persistent Job Queue** - Jobs survive restarts (SQLite storage)
- ✅ **Multiple Schedule Types** - Daily, weekly, interval, and cron schedules
- ✅ **One-time Jobs** - Queue immediate downloads on-demand
- ✅ **Concurrent Execution** - Run multiple jobs in parallel
- ✅ **Automatic Retry** - Configurable retry logic with exponential backoff
- ✅ **Comprehensive Logging** - Track all job executions and errors
- ✅ **Cross-platform** - Works on Linux, macOS, and Windows

## Quick Start

### 1. Install

```bash
pip install -e .
```

This installs APScheduler and other required dependencies.

### 2. Initialize

```bash
earnings-scheduler init
```

Creates default configuration at `~/.earnings_data/scheduler_config.json`

### 3. Start Scheduler

```bash
# Background mode (daemon)
earnings-scheduler start

# Foreground mode (for testing/debugging)
earnings-scheduler start --foreground
```

### 4. Check Status

```bash
earnings-scheduler status
earnings-scheduler list
```

## CLI Commands

### Scheduler Management

```bash
# Start scheduler
earnings-scheduler start [--foreground] [--workers N]

# Stop scheduler
earnings-scheduler stop

# Show status
earnings-scheduler status

# Initialize configuration
earnings-scheduler init

# Show current configuration
earnings-scheduler show-config
```

### Job Management

```bash
# List all configured jobs
earnings-scheduler list

# Add a new scheduled job
earnings-scheduler add <name> --type <type> [schedule] [options]

# Remove a job
earnings-scheduler remove <job_name>

# Enable/disable a job
earnings-scheduler enable <job_name>
earnings-scheduler disable <job_name>

# Run a one-time job
earnings-scheduler run-once --type <type> [options]
```

## Schedule Types

### Daily Schedule

Run a job every day at a specific time:

```bash
earnings-scheduler add daily_transcripts \
  --type transcripts \
  --daily \
  --time "02:00"
```

### Weekly Schedule

Run a job on a specific day of the week:

```bash
earnings-scheduler add weekly_sync \
  --type transcripts \
  --weekly \
  --day monday \
  --time "03:00" \
  --all
```

### Interval Schedule

Run a job at regular intervals:

```bash
# Every 6 hours
earnings-scheduler add monitor_filings \
  --type sec \
  --interval \
  --hours 6

# Every 30 minutes
earnings-scheduler add frequent_check \
  --type transcripts \
  --interval \
  --minutes 30
```

### Cron Schedule

Use cron expressions for complex schedules:

```bash
# First day of every month at 5 AM
earnings-scheduler add monthly_reindex \
  --type index \
  --cron "0 5 1 * *"

# Every weekday at 9 AM
earnings-scheduler add weekday_download \
  --type transcripts \
  --cron "0 9 * * 1-5"
```

**Cron format:** `minute hour day month day_of_week`

## Job Types

### 1. Transcripts (`transcripts`)

Download earnings call transcripts from Motley Fool.

**Options:**
- `--ticker SYMBOL` - Download specific ticker
- `--all` - Download all historical transcripts
- `--from YYYY-MM` - Start date
- `--to YYYY-MM` - End date

**Examples:**

```bash
# Daily download of current month
earnings-scheduler add daily_transcripts \
  --type transcripts \
  --daily --time "02:00"

# Weekly full historical sync
earnings-scheduler add weekly_all \
  --type transcripts \
  --weekly --day sunday --time "03:00" \
  --all

# Specific ticker every 4 hours
earnings-scheduler add aapl_monitor \
  --type transcripts \
  --interval --hours 4 \
  --ticker AAPL
```

### 2. SEC Filings (`sec`)

Download SEC filings (10-K, 10-Q).

**Options:**
- `--ticker SYMBOL [SYMBOL...]` - One or more tickers (required)
- `--forms FORM [FORM...]` - Form types (default: 10-K 10-Q)
- `--all` - Download all historical filings
- `--from YYYY-MM-DD` - Start date
- `--to YYYY-MM-DD` - End date

**Examples:**

```bash
# Monitor major tech companies every 6 hours
earnings-scheduler add tech_sec_monitor \
  --type sec \
  --interval --hours 6 \
  --ticker AAPL MSFT GOOGL AMZN \
  --forms 10-K 10-Q
```

**Note:** SEC job type requires tickers to be specified in the configuration file.

### 3. Indexing (`index`)

Rebuild or update the SQLite metadata index.

**Options:**
- `--rebuild` - Full rebuild (slower but thorough)

**Examples:**

```bash
# Daily index update after transcripts download
earnings-scheduler add daily_index \
  --type index \
  --daily --time "04:00"

# Monthly full rebuild
earnings-scheduler add monthly_rebuild \
  --type index \
  --cron "0 5 1 * *" \
  --rebuild
```

## One-Time Jobs (Dynamic Queue)

Queue jobs to run immediately or at a specific time without adding to the schedule:

```bash
# Run immediately
earnings-scheduler run-once \
  --type transcripts \
  --ticker NVDA

# Run at specific time
earnings-scheduler run-once \
  --type transcripts \
  --all \
  --at "2024-12-27 15:00"

# Download specific date range
earnings-scheduler run-once \
  --type transcripts \
  --from 2024-01 --to 2024-06
```

One-time jobs are automatically removed after execution.

## Configuration

Configuration file: `~/.earnings_data/scheduler_config.json`

### Basic Example

```json
{
  "schedules": [
    {
      "name": "daily_transcripts",
      "enabled": true,
      "job_type": "transcripts",
      "schedule": {
        "type": "daily",
        "time": "02:00"
      },
      "options": {}
    }
  ],
  "logging": {
    "level": "INFO",
    "file": "~/.earnings_data/logs/scheduler.log",
    "rotation": "daily",
    "retention_days": 30
  },
  "error_handling": {
    "max_retries": 3,
    "retry_delay_minutes": 15,
    "send_notifications": false,
    "notification_email": null
  }
}
```

### Advanced Example

See `scheduler/examples/advanced_schedule.json` for a comprehensive example with:
- Daily current month downloads
- Weekly historical sync
- Interval-based SEC filing monitoring
- Index rebuilding

## Logging

Logs are written to `~/.earnings_data/logs/scheduler.log` by default.

**View logs:**

```bash
# Tail logs
tail -f ~/.earnings_data/logs/scheduler.log

# View recent errors
grep ERROR ~/.earnings_data/logs/scheduler.log | tail -20

# Watch job executions
grep "Job.*completed" ~/.earnings_data/logs/scheduler.log
```

**Log levels:**
- `INFO` - Job start/completion, schedule changes
- `WARNING` - Retries, missed schedules
- `ERROR` - Job failures, configuration errors
- `DEBUG` - Detailed execution traces (use `--verbose`)

## Error Handling

The scheduler includes robust error handling:

1. **Automatic Retry** - Failed jobs are retried up to 3 times (configurable)
2. **Exponential Backoff** - Retry delays: 15, 30, 60 minutes (configurable)
3. **Job Isolation** - One job's failure doesn't affect others
4. **Detailed Logging** - All errors logged with stack traces
5. **Graceful Degradation** - Scheduler continues running despite job failures

**Configure in `scheduler_config.json`:**

```json
{
  "error_handling": {
    "max_retries": 3,
    "retry_delay_minutes": 15,
    "send_notifications": false,
    "notification_email": null
  }
}
```

## Job Storage

Jobs are stored in a persistent SQLite database:
- Location: `~/.earnings_data/scheduler_jobs.db`
- Jobs survive scheduler restarts
- Next run times automatically calculated
- Missed jobs handled intelligently (coalescing)

## Common Use Cases

### 1. Daily New Transcripts

Download only new transcripts every day:

```bash
earnings-scheduler add daily_new \
  --type transcripts \
  --daily --time "02:00"
```

Configuration downloads current month by default (new transcripts only).

### 2. Weekly Full Sync

Comprehensive historical sync once per week:

```bash
earnings-scheduler add weekly_full_sync \
  --type transcripts \
  --weekly --day sunday --time "03:00" \
  --all
```

### 3. Continuous Monitoring

Monitor specific tickers throughout the day:

```bash
# Monitor FAANG stocks every 4 hours
for ticker in AAPL MSFT GOOGL AMZN; do
  earnings-scheduler add "${ticker}_monitor" \
    --type transcripts \
    --interval --hours 4 \
    --ticker $ticker
done
```

### 4. SEC Filing Alerts

Check for new SEC filings periodically:

```bash
# Configure in scheduler_config.json
{
  "name": "sec_monitor",
  "job_type": "sec",
  "schedule": {"type": "interval", "hours": 6},
  "options": {
    "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN"],
    "forms": ["10-K", "10-Q"]
  }
}
```

### 5. Index Maintenance

Keep index updated:

```bash
# Daily update
earnings-scheduler add daily_index \
  --type index \
  --daily --time "04:00"

# Monthly full rebuild
earnings-scheduler add monthly_rebuild \
  --type index \
  --cron "0 5 1 * *"
```

## Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/earnings-scheduler.service`:

```ini
[Unit]
Description=Earnings Transcript Scheduler
After=network.target

[Service]
Type=simple
User=your_username
ExecStart=/path/to/venv/bin/earnings-scheduler start --foreground
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable earnings-scheduler
sudo systemctl start earnings-scheduler
sudo systemctl status earnings-scheduler
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -e .

# Initialize configuration
RUN earnings-scheduler init

CMD ["earnings-scheduler", "start", "--foreground"]
```

Build and run:

```bash
docker build -t earnings-scheduler .
docker run -d \
  --name earnings-scheduler \
  -v ~/.earnings_data:/root/.earnings_data \
  earnings-scheduler
```

### Cron (Legacy Alternative)

If you prefer traditional cron:

```bash
# Edit crontab
crontab -e

# Add daily download at 2 AM
0 2 * * * /path/to/venv/bin/earnings-download-transcripts >> /var/log/earnings.log 2>&1
```

**Note:** Cron approach lacks dynamic job management and persistent queue features.

## Troubleshooting

### Scheduler Won't Start

```bash
# Check configuration
earnings-scheduler show-config

# Validate configuration
python -c "from scheduler.config import SchedulerConfig; c = SchedulerConfig(); print(c.validate())"

# Check logs
tail -50 ~/.earnings_data/logs/scheduler.log
```

### Jobs Not Running

```bash
# Check scheduler status
earnings-scheduler status

# List all jobs
earnings-scheduler list

# Verify job is enabled
# Edit ~/.earnings_data/scheduler_config.json
# Set "enabled": true
```

### Job Failures

```bash
# Check error logs
grep ERROR ~/.earnings_data/logs/scheduler.log | tail -20

# Run job manually to test
earnings-scheduler run-once --type transcripts --ticker AAPL

# Increase retry attempts
# Edit scheduler_config.json: "max_retries": 5
```

### Database Issues

```bash
# Check job store database
sqlite3 ~/.earnings_data/scheduler_jobs.db "SELECT * FROM apscheduler_jobs;"

# Reset job store (WARNING: removes all scheduled jobs)
rm ~/.earnings_data/scheduler_jobs.db
earnings-scheduler start
```

## Architecture

```
scheduler/
├── __init__.py       # Package initialization
├── config.py         # Configuration management
├── jobs.py           # Job definitions and execution
├── service.py        # Core scheduler service (APScheduler)
├── cli.py            # Command-line interface
└── examples/         # Example configurations
    ├── basic_schedule.json
    └── advanced_schedule.json
```

**Key Components:**

1. **SchedulerService** - Manages APScheduler instance and job lifecycle
2. **JobManager** - Executes different job types with retry logic
3. **SchedulerConfig** - Handles configuration loading/saving
4. **CLI** - Provides comprehensive command-line interface

## API (Programmatic Usage)

```python
from scheduler.service import SchedulerService
from scheduler.config import SchedulerConfig, JobConfig, ScheduleConfig

# Create scheduler
service = SchedulerService()

# Add a job programmatically
job = JobConfig(
    name="my_custom_job",
    job_type="transcripts",
    enabled=True,
    schedule=ScheduleConfig(type="daily", time="10:00"),
    options={"ticker": "TSLA"}
)

config = SchedulerConfig()
config.add_job(job)
config.save()

# Start scheduler
service.start()

# Queue one-time job
service.add_one_time_job(
    job_type="transcripts",
    options={"ticker": "NVDA"}
)

# Get job status
jobs = service.get_jobs()
for job in jobs:
    print(f"{job['id']}: next run at {job['next_run']}")
```

## Performance

- **Concurrent Jobs**: Up to 5 jobs run in parallel (configurable with `--workers`)
- **Memory Usage**: ~50-100MB for scheduler process
- **Database Size**: Job store typically < 1MB
- **Job Overhead**: ~1-2 seconds per job startup

## Security

- **No network exposure** - Runs locally only
- **File permissions** - Config files readable only by user
- **No credentials storage** - Uses existing authentication
- **Isolated execution** - Jobs run in separate threads

## Limitations

- **Single machine** - Not designed for distributed deployment
- **No web UI** - CLI and config file only
- **Local storage** - Job store is SQLite (not Redis/PostgreSQL)
- **No job priorities** - All jobs treated equally

For distributed deployment or advanced features, consider upgrading to Celery or Airflow.

## FAQ

**Q: Can I run multiple schedulers?**
A: No, only one scheduler instance should run at a time to avoid duplicate executions.

**Q: What happens if my computer is off during a scheduled time?**
A: Missed jobs are coalesced and run once when the scheduler starts.

**Q: Can I modify schedules without restarting?**
A: Not currently. Restart the scheduler after modifying `scheduler_config.json`.

**Q: How do I download for all companies every day?**
A: Use `--all` option in a daily schedule:
```bash
earnings-scheduler add daily_all \
  --type transcripts \
  --daily --time "02:00" \
  --all
```

**Q: Can I get email notifications?**
A: Email notifications are planned but not yet implemented.

## Support

- **Issues**: https://github.com/arunsmiles/earningstranscripts/issues
- **Documentation**: See README.md, USAGE.md, QUICKSTART.md
- **Examples**: `scheduler/examples/`

## License

MIT License - see LICENSE file for details.
