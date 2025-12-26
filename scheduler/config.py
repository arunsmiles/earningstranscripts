"""
Scheduler configuration management.

Handles loading, saving, and validating scheduler configuration including
job definitions, logging settings, and error handling policies.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ScheduleConfig:
    """Schedule timing configuration."""
    type: str  # 'daily', 'weekly', 'interval', 'cron'
    time: Optional[str] = None  # HH:MM for daily
    day: Optional[str] = None  # monday, tuesday, etc. for weekly
    hours: Optional[int] = None  # interval in hours
    minutes: Optional[int] = None  # interval in minutes
    cron: Optional[str] = None  # cron expression


@dataclass
class JobConfig:
    """Individual job configuration."""
    name: str
    job_type: str  # 'transcripts', 'sec', 'index', 'custom'
    enabled: bool
    schedule: ScheduleConfig
    options: Dict[str, Any]


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "~/.earnings_data/logs/scheduler.log"
    rotation: str = "daily"
    retention_days: int = 30
    max_bytes: int = 10 * 1024 * 1024  # 10MB


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
    """

    DEFAULT_CONFIG_PATH = Path.home() / ".earnings_data" / "scheduler_config.json"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize scheduler configuration.

        Args:
            config_path: Path to configuration file. If None, uses default.
        """
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
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
                    job_type=job_data['job_type'],
                    enabled=job_data.get('enabled', True),
                    schedule=schedule,
                    options=job_data.get('options', {})
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
                    'enabled': job.enabled,
                    'job_type': job.job_type,
                    'schedule': asdict(job.schedule),
                    'options': job.options
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
            job_type="transcripts",
            enabled=True,
            schedule=ScheduleConfig(type="daily", time="02:00"),
            options={}  # Downloads current month
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
            # Validate job type
            if job.job_type not in ['transcripts', 'sec', 'index', 'custom']:
                errors.append(f"Job {job.name}: Invalid job_type '{job.job_type}'")

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

        return errors

    def __repr__(self):
        return f"SchedulerConfig(jobs={len(self.jobs)}, path={self.config_path})"
