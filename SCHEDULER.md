# Generic Command Scheduler

A production-ready scheduling system for running any shell command on a schedule. Completely decoupled from specific tools - just specify your commands and when to run them.

## Features

- ✅ **Generic Command Execution** - Run any shell command on a schedule
- ✅ **Completely Decoupled** - Scheduler knows nothing about your tools
- ✅ **Dynamic Job Management** - Add, remove, and modify jobs at runtime
- ✅ **Persistent Job Queue** - Jobs survive restarts (SQLite storage)
- ✅ **Multiple Schedule Types** - Daily, weekly, interval, and cron schedules
- ✅ **One-time Jobs** - Queue immediate execution on-demand
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
job-scheduler init
```

Creates default configuration at `~/.earnings_data/scheduler_config.json`

### 3. Start Scheduler

```bash
# Background mode (daemon)
job-scheduler start

# Foreground mode (for testing/debugging)
job-scheduler start --foreground
```

### 4. Check Status

```bash
job-scheduler status
job-scheduler list
```

## CLI Commands

### Scheduler Management

```bash
# Start scheduler
job-scheduler start [--foreground] [--workers N]

# Stop scheduler
job-scheduler stop

# Show status
job-scheduler status

# Initialize configuration
job-scheduler init

# Show current configuration
job-scheduler show-config
```

### Job Management

```bash
# List all configured jobs
job-scheduler list

# Add a new scheduled job (any shell command)
job-scheduler add <name> --command "<shell_command>" [schedule options]

# Remove a job
job-scheduler remove <job_name>

# Enable/disable a job
job-scheduler enable <job_name>
job-scheduler disable <job_name>

# Run a one-time command
job-scheduler run-once --command "<shell_command>"
```

## Schedule Types

### Daily Schedule

Run a command every day at a specific time:

```bash
job-scheduler add daily_transcripts \
  --command "earnings-download-transcripts" \
  --daily \
  --time "02:00"
```

### Weekly Schedule

Run a command on a specific day of the week:

```bash
job-scheduler add weekly_sync \
  --command "earnings-download-transcripts --all" \
  --weekly \
  --day sunday \
  --time "03:00"
```

### Interval Schedule

Run a command at regular intervals:

```bash
# Every 6 hours
job-scheduler add monitor_filings \
  --command "earnings-download-sec --ticker AAPL MSFT" \
  --interval \
  --hours 6

# Every 30 minutes
job-scheduler add frequent_check \
  --command "python /path/to/check_script.py" \
  --interval \
  --minutes 30
```

### Cron Schedule

Use cron expressions for complex schedules:

```bash
# First day of every month at 5 AM
job-scheduler add monthly_reindex \
  --command "earnings-index --rebuild" \
  --cron "0 5 1 * *"

# Every weekday at 9 AM
job-scheduler add weekday_download \
  --command "earnings-download-transcripts" \
  --cron "0 9 * * 1-5"
```

**Cron format:** `minute hour day month day_of_week`

## Examples

### Earnings Transcript Downloads

```bash
# Daily download of current month transcripts
job-scheduler add daily_transcripts \
  --command "earnings-download-transcripts" \
  --daily --time "02:00"

# Weekly full historical sync
job-scheduler add weekly_all \
  --command "earnings-download-transcripts --all --delay 2.0" \
  --weekly --day sunday --time "03:00"

# Specific ticker every 4 hours
job-scheduler add aapl_monitor \
  --command "earnings-download-transcripts --ticker AAPL" \
  --interval --hours 4
```

### SEC Filings

```bash
# Monitor major tech companies every 6 hours
job-scheduler add tech_sec_monitor \
  --command "earnings-download-sec --ticker AAPL MSFT GOOGL AMZN --forms 10-K 10-Q" \
  --interval --hours 6
```

### Index Maintenance

```bash
# Daily index update after transcripts download
job-scheduler add daily_index \
  --command "earnings-index --update" \
  --daily --time "04:00"

# Monthly full rebuild
job-scheduler add monthly_rebuild \
  --command "earnings-index --rebuild" \
  --cron "0 5 1 * *"
```

### Custom Scripts

Run any script or command - the scheduler doesn't care what it does:

```bash
# Run a Python script
job-scheduler add custom_analysis \
  --command "python /path/to/analyze.py --output /tmp/report.csv" \
  --daily --time "06:00"

# Run a shell script
job-scheduler add backup_data \
  --command "/path/to/backup.sh" \
  --weekly --day saturday --time "01:00"

# Chain multiple commands
job-scheduler add pipeline \
  --command "earnings-download-transcripts && earnings-index --update" \
  --daily --time "02:30"
```

## One-Time Jobs (Dynamic Queue)

Run commands immediately or at a specific time without adding to the schedule:

```bash
# Run immediately
job-scheduler run-once \
  --command "earnings-download-transcripts --ticker NVDA"

# Run at specific time
job-scheduler run-once \
  --command "earnings-download-transcripts --all" \
  --at "2024-12-27 15:00"

# Run any command
job-scheduler run-once \
  --command "python /path/to/my_script.py --arg value"
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
      "command": "earnings-download-transcripts",
      "schedule": {
        "type": "daily",
        "time": "02:00"
      },
      "timeout": 3600,
      "description": "Download current month transcripts daily"
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
- Daily transcript downloads
- Weekly historical sync
- Interval-based SEC filing monitoring
- Index rebuilding
- Custom script execution

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
job-scheduler add daily_new \
  --command "earnings-download-transcripts" \
  --daily --time "02:00"
```

### 2. Weekly Full Sync

Comprehensive historical sync once per week:

```bash
job-scheduler add weekly_full_sync \
  --command "earnings-download-transcripts --all" \
  --weekly --day sunday --time "03:00"
```

### 3. Continuous Monitoring

Monitor specific tickers throughout the day:

```bash
# Monitor FAANG stocks every 4 hours
for ticker in AAPL MSFT GOOGL AMZN; do
  job-scheduler add "${ticker}_monitor" \
    --command "earnings-download-transcripts --ticker $ticker" \
    --interval --hours 4
done
```

### 4. SEC Filing Alerts

Check for new SEC filings periodically:

```bash
job-scheduler add sec_monitor \
  --command "earnings-download-sec --ticker AAPL MSFT GOOGL AMZN --forms 10-K 10-Q" \
  --interval --hours 6
```

### 5. Index Maintenance

Keep index updated:

```bash
# Daily update
job-scheduler add daily_index \
  --command "earnings-index --update" \
  --daily --time "04:00"

# Monthly full rebuild
job-scheduler add monthly_rebuild \
  --command "earnings-index --rebuild" \
  --cron "0 5 1 * *"
```

### 6. Custom Pipelines

Chain multiple commands together:

```bash
# Download transcripts, then update index
job-scheduler add daily_pipeline \
  --command "earnings-download-transcripts && earnings-index --update" \
  --daily --time "02:00"
```

## Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/job-scheduler.service`:

```ini
[Unit]
Description=Earnings Transcript Scheduler
After=network.target

[Service]
Type=simple
User=your_username
ExecStart=/path/to/venv/bin/job-scheduler start --foreground
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable job-scheduler
sudo systemctl start job-scheduler
sudo systemctl status job-scheduler
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -e .

# Initialize configuration
RUN job-scheduler init

CMD ["job-scheduler", "start", "--foreground"]
```

Build and run:

```bash
docker build -t job-scheduler .
docker run -d \
  --name job-scheduler \
  -v ~/.earnings_data:/root/.earnings_data \
  job-scheduler
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
job-scheduler show-config

# Validate configuration
python -c "from scheduler.config import SchedulerConfig; c = SchedulerConfig(); print(c.validate())"

# Check logs
tail -50 ~/.earnings_data/logs/scheduler.log
```

### Jobs Not Running

```bash
# Check scheduler status
job-scheduler status

# List all jobs
job-scheduler list

# Verify job is enabled
# Edit ~/.earnings_data/scheduler_config.json
# Set "enabled": true
```

### Job Failures

```bash
# Check error logs
grep ERROR ~/.earnings_data/logs/scheduler.log | tail -20

# Run job manually to test
job-scheduler run-once --command "earnings-download-transcripts --ticker AAPL"

# Increase retry attempts
# Edit scheduler_config.json: "max_retries": 5
```

### Database Issues

```bash
# Check job store database
sqlite3 ~/.earnings_data/scheduler_jobs.db "SELECT * FROM apscheduler_jobs;"

# Reset job store (WARNING: removes all scheduled jobs)
rm ~/.earnings_data/scheduler_jobs.db
job-scheduler start
```

## Architecture

```
scheduler/
├── __init__.py       # Package initialization
├── config.py         # Configuration management
├── jobs.py           # Generic command execution
├── service.py        # Core scheduler service (APScheduler)
├── cli.py            # Command-line interface
└── examples/         # Example configurations
    ├── basic_schedule.json
    └── advanced_schedule.json
```

**Key Components:**

1. **SchedulerService** - Manages APScheduler instance and job lifecycle
2. **CommandExecutor** - Executes shell commands with retry logic
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
    command="earnings-download-transcripts --ticker TSLA",
    enabled=True,
    schedule=ScheduleConfig(type="daily", time="10:00"),
    description="Download TSLA transcripts daily"
)

config = SchedulerConfig()
config.add_job(job)
config.save()

# Start scheduler
service.start()

# Queue one-time job
service.add_one_time_job(
    command="earnings-download-transcripts --ticker NVDA"
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
A: Use `--all` option in your command:
```bash
job-scheduler add daily_all \
  --command "earnings-download-transcripts --all" \
  --daily --time "02:00"
```

**Q: Can I run any shell command?**
A: Yes! The scheduler is completely generic. Run Python scripts, shell scripts, or any executable:
```bash
job-scheduler add my_job \
  --command "python /path/to/script.py --arg value" \
  --daily --time "10:00"
```

**Q: Can I get email notifications?**
A: Email notifications are planned but not yet implemented.

## Support

- **Issues**: https://github.com/arunsmiles/earningstranscripts/issues
- **Documentation**: See README.md, USAGE.md, QUICKSTART.md
- **Examples**: `scheduler/examples/`

## License

MIT License - see LICENSE file for details.
