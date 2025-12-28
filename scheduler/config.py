"""
Scheduler configuration management.

Handles loading, saving, and validating scheduler configuration.
The scheduler is generic and command-based - it simply stores and
executes shell commands on a schedule.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ScheduleConfig:
    """Schedule timing configuration."""
    type: str  # 'daily', 'weekly', 'interval', 'cron'
    time: Optional[str] = None  # HH:MM for daily/weekly
    day: Optional[str] = None  # monday, tuesday, etc. for weekly
    hours: Optional[int] = None  # interval in hours
    minutes: Optional[int] = None  # interval in minutes
    cron: Optional[str] = None  # cron expression


@dataclass
class JobConfig:
    """
    Individual job configuration.

    Jobs are command-based - the scheduler doesn't know or care what
    the command does. It just executes it on the specified schedule.
    """
    name: str
    command: str  # Shell command to execute
    enabled: bool
    schedule: ScheduleConfig
    timeout: int = 3600  # Command timeout in seconds (default: 1 hour)
    working_dir: Optional[str] = None  # Working directory for command
    description: Optional[str] = None  # Human-readable description


def _get_default_log_file() -> str:
    """Get default log file path from environment or default."""
    if os.environ.get('SCHEDULER_LOG_DIR'):
        return str(Path(os.environ['SCHEDULER_LOG_DIR']).expanduser() / "scheduler.log")
    elif os.environ.get('EARNINGS_DATA_DIR'):
        return str(Path(os.environ['EARNINGS_DATA_DIR']).expanduser() / "logs" / "scheduler.log")
    else:
        return "~/.earnings_data/logs/scheduler.log"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = None  # Set dynamically in __post_init__
    rotation: str = "daily"
    retention_days: int = 30
    max_bytes: int = 10 * 1024 * 1024  # 10MB

    def __post_init__(self):
        if self.file is None:
            self.file = _get_default_log_file()


@dataclass
class ErrorHandlingConfig:
    """Error handling and retry configuration."""
    max_retries: int = 3
    retry_delay_minutes: int = 15
    send_notifications: bool = False
    notification_email: Optional[str] = None


class SchedulerConfig:
    """
    Scheduler configuration manager.

    Loads and manages scheduler configuration from JSON file,
    with support for validation and defaults.

    Configuration path priority:
    1. Explicit config_path argument
    2. SCHEDULER_CONFIG_PATH environment variable
    3. Default: ~/.earnings_data/scheduler_config.json
    """

    DEFAULT_CONFIG_PATH = Path.home() / ".earnings_data" / "scheduler_config.json"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize scheduler configuration.

        Args:
            config_path: Path to configuration file. If None, uses env var or default.
        """
        if config_path:
            self.config_path = Path(config_path)
        elif os.environ.get('SCHEDULER_CONFIG_PATH'):
            self.config_path = Path(os.environ['SCHEDULER_CONFIG_PATH']).expanduser()
        else:
            self.config_path = self.DEFAULT_CONFIG_PATH
        self.jobs: List[JobConfig] = []
        self.logging: LoggingConfig = LoggingConfig()
        self.error_handling: ErrorHandlingConfig = ErrorHandlingConfig()

        if self.config_path.exists():
            self.load()
        else:
            logger.info(f"No config found at {self.config_path}, using defaults")
            self._load_defaults()

    def load(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)

            # Load jobs
            self.jobs = []
            for job_data in data.get('schedules', []):
                schedule_data = job_data['schedule']
                schedule = ScheduleConfig(**schedule_data)

                job = JobConfig(
                    name=job_data['name'],
                    command=job_data['command'],
                    enabled=job_data.get('enabled', True),
                    schedule=schedule,
                    timeout=job_data.get('timeout', 3600),
                    working_dir=job_data.get('working_dir'),
                    description=job_data.get('description')
                )
                self.jobs.append(job)

            # Load logging config
            if 'logging' in data:
                self.logging = LoggingConfig(**data['logging'])

            # Load error handling config
            if 'error_handling' in data:
                self.error_handling = ErrorHandlingConfig(**data['error_handling'])

            logger.info(f"Loaded {len(self.jobs)} job(s) from {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise

    def save(self):
        """Save configuration to JSON file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'schedules': [
                {
                    'name': job.name,
                    'command': job.command,
                    'enabled': job.enabled,
                    'schedule': asdict(job.schedule),
                    'timeout': job.timeout,
                    'working_dir': job.working_dir,
                    'description': job.description
                }
                for job in self.jobs
            ],
            'logging': asdict(self.logging),
            'error_handling': asdict(self.error_handling)
        }

        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved configuration to {self.config_path}")

    def _load_defaults(self):
        """Load default configuration."""
        # Default: Daily transcript download at 2 AM
        default_job = JobConfig(
            name="daily_transcripts",
            command="earnings-download-transcripts",
            enabled=True,
            schedule=ScheduleConfig(type="daily", time="02:00"),
            description="Download current month transcripts daily"
        )
        self.jobs = [default_job]

    def add_job(self, job: JobConfig):
        """Add a new job to configuration."""
        # Check for duplicate names
        if any(j.name == job.name for j in self.jobs):
            raise ValueError(f"Job with name '{job.name}' already exists")

        self.jobs.append(job)
        logger.info(f"Added job: {job.name}")

    def remove_job(self, name: str) -> bool:
        """
        Remove a job by name.

        Returns:
            True if job was removed, False if not found
        """
        initial_len = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.name != name]

        if len(self.jobs) < initial_len:
            logger.info(f"Removed job: {name}")
            return True
        return False

    def get_job(self, name: str) -> Optional[JobConfig]:
        """Get job configuration by name."""
        for job in self.jobs:
            if job.name == name:
                return job
        return None

    def update_job(self, name: str, **kwargs):
        """Update job configuration."""
        job = self.get_job(name)
        if not job:
            raise ValueError(f"Job '{name}' not found")

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        logger.info(f"Updated job: {name}")

    def enable_job(self, name: str):
        """Enable a job."""
        self.update_job(name, enabled=True)

    def disable_job(self, name: str):
        """Disable a job."""
        self.update_job(name, enabled=False)

    def get_enabled_jobs(self) -> List[JobConfig]:
        """Get list of enabled jobs."""
        return [j for j in self.jobs if j.enabled]

    def validate(self) -> List[str]:
        """
        Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        for job in self.jobs:
            # Validate command is not empty
            if not job.command or not job.command.strip():
                errors.append(f"Job {job.name}: 'command' cannot be empty")

            # Validate schedule
            schedule = job.schedule
            if schedule.type == 'daily' and not schedule.time:
                errors.append(f"Job {job.name}: 'daily' schedule requires 'time'")
            elif schedule.type == 'weekly' and (not schedule.day or not schedule.time):
                errors.append(f"Job {job.name}: 'weekly' schedule requires 'day' and 'time'")
            elif schedule.type == 'interval' and not (schedule.hours or schedule.minutes):
                errors.append(f"Job {job.name}: 'interval' schedule requires 'hours' or 'minutes'")
            elif schedule.type == 'cron' and not schedule.cron:
                errors.append(f"Job {job.name}: 'cron' schedule requires 'cron' expression")

            # Validate timeout
            if job.timeout <= 0:
                errors.append(f"Job {job.name}: 'timeout' must be positive")

        return errors

    def __repr__(self):
        return f"SchedulerConfig(jobs={len(self.jobs)}, path={self.config_path})"
