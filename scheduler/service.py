"""
Core scheduler service using APScheduler.

Provides a production-ready scheduling system with:
- Persistent job storage (SQLite)
- Dynamic job management
- Concurrent execution
- Job event logging
"""

import logging
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    EVENT_JOB_ADDED,
    EVENT_JOB_REMOVED
)

from scheduler.config import SchedulerConfig, JobConfig, ScheduleConfig
from scheduler.jobs import JobManager, JobExecutionError

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Main scheduler service managing job execution.

    Uses APScheduler with SQLite job store for persistence.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        job_store_path: Optional[str] = None,
        max_workers: int = 5,
        foreground: bool = False
    ):
        """
        Initialize scheduler service.

        Args:
            config_path: Path to scheduler configuration file
            job_store_path: Path to SQLite job store database
            max_workers: Maximum number of concurrent job executions
            foreground: If True, use blocking scheduler (for foreground mode)
        """
        self.config = SchedulerConfig(config_path)
        self.job_manager = JobManager()

        # Setup job store
        if not job_store_path:
            job_store_path = str(Path.home() / ".earnings_data" / "scheduler_jobs.db")

        # Ensure directory exists
        Path(job_store_path).parent.mkdir(parents=True, exist_ok=True)

        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{job_store_path}')
        }

        # Setup executors
        executors = {
            'default': ThreadPoolExecutor(max_workers)
        }

        # Job defaults
        job_defaults = {
            'coalesce': True,  # Combine multiple missed runs into one
            'max_instances': 1,  # Prevent concurrent runs of same job
            'misfire_grace_time': 300  # 5 minutes grace period
        }

        # Create scheduler
        if foreground:
            self.scheduler = BlockingScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults
            )
        else:
            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults
            )

        # Setup event listeners
        self._setup_event_listeners()

        # Setup signal handlers
        self._setup_signal_handlers()

        logger.info(f"Scheduler initialized with job store: {job_store_path}")

    def _setup_event_listeners(self):
        """Setup APScheduler event listeners for logging."""

        def job_executed_listener(event):
            logger.info(
                f"Job '{event.job_id}' executed successfully "
                f"(runtime: {event.retval if hasattr(event, 'retval') else 'N/A'})"
            )

        def job_error_listener(event):
            logger.error(
                f"Job '{event.job_id}' raised exception: {event.exception}",
                exc_info=True
            )

        def job_missed_listener(event):
            logger.warning(f"Job '{event.job_id}' missed scheduled run time")

        def job_added_listener(event):
            logger.info(f"Job '{event.job_id}' added to scheduler")

        def job_removed_listener(event):
            logger.info(f"Job '{event.job_id}' removed from scheduler")

        self.scheduler.add_listener(job_executed_listener, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
        self.scheduler.add_listener(job_missed_listener, EVENT_JOB_MISSED)
        self.scheduler.add_listener(job_added_listener, EVENT_JOB_ADDED)
        self.scheduler.add_listener(job_removed_listener, EVENT_JOB_REMOVED)

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def load_jobs_from_config(self):
        """Load and register jobs from configuration file."""
        errors = self.config.validate()
        if errors:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            raise ValueError("Invalid configuration")

        enabled_jobs = self.config.get_enabled_jobs()
        logger.info(f"Loading {len(enabled_jobs)} enabled job(s) from configuration")

        for job_config in enabled_jobs:
            try:
                self.add_job_from_config(job_config)
            except Exception as e:
                logger.error(f"Failed to load job '{job_config.name}': {e}")

    def add_job_from_config(self, job_config: JobConfig):
        """
        Add a job to the scheduler from JobConfig.

        Args:
            job_config: Job configuration object
        """
        # Create job function
        job_func = self.job_manager.create_job_function(
            job_config.job_type,
            job_config.options
        )

        # Wrap with retry logic
        def wrapped_job():
            return self.job_manager.execute_with_retry(
                job_func,
                job_config.name,
                max_retries=self.config.error_handling.max_retries,
                retry_delay_minutes=self.config.error_handling.retry_delay_minutes
            )

        # Add to scheduler based on schedule type
        schedule = job_config.schedule

        if schedule.type == 'daily':
            self.scheduler.add_job(
                wrapped_job,
                'cron',
                hour=int(schedule.time.split(':')[0]),
                minute=int(schedule.time.split(':')[1]),
                id=job_config.name,
                replace_existing=True
            )

        elif schedule.type == 'weekly':
            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            self.scheduler.add_job(
                wrapped_job,
                'cron',
                day_of_week=day_map.get(schedule.day.lower(), 0),
                hour=int(schedule.time.split(':')[0]),
                minute=int(schedule.time.split(':')[1]),
                id=job_config.name,
                replace_existing=True
            )

        elif schedule.type == 'interval':
            kwargs = {}
            if schedule.hours:
                kwargs['hours'] = schedule.hours
            if schedule.minutes:
                kwargs['minutes'] = schedule.minutes

            self.scheduler.add_job(
                wrapped_job,
                'interval',
                **kwargs,
                id=job_config.name,
                replace_existing=True
            )

        elif schedule.type == 'cron':
            # Parse cron expression (assumes standard cron format)
            self.scheduler.add_job(
                wrapped_job,
                'cron',
                **self._parse_cron_expression(schedule.cron),
                id=job_config.name,
                replace_existing=True
            )

        logger.info(f"Added job '{job_config.name}' with schedule type '{schedule.type}'")

    def _parse_cron_expression(self, cron_expr: str) -> Dict[str, Any]:
        """
        Parse cron expression into APScheduler kwargs.

        Args:
            cron_expr: Cron expression (e.g., "0 2 * * *")

        Returns:
            Dict of APScheduler cron parameters
        """
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")

        return {
            'minute': parts[0],
            'hour': parts[1],
            'day': parts[2],
            'month': parts[3],
            'day_of_week': parts[4]
        }

    def add_one_time_job(
        self,
        job_type: str,
        options: Dict[str, Any],
        run_at: Optional[datetime] = None,
        job_id: Optional[str] = None
    ) -> str:
        """
        Add a one-time job to run immediately or at a specific time.

        Args:
            job_type: Type of job to run
            options: Job options
            run_at: When to run the job (None = immediately)
            job_id: Optional job ID (auto-generated if not provided)

        Returns:
            Job ID
        """
        job_func = self.job_manager.create_job_function(job_type, options)

        if not job_id:
            job_id = f"onetime_{job_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if run_at:
            self.scheduler.add_job(
                job_func,
                'date',
                run_date=run_at,
                id=job_id,
                replace_existing=True
            )
            logger.info(f"Scheduled one-time job '{job_id}' for {run_at}")
        else:
            # Run immediately
            self.scheduler.add_job(
                job_func,
                'date',
                run_date=datetime.now(),
                id=job_id,
                replace_existing=True
            )
            logger.info(f"Scheduled one-time job '{job_id}' to run immediately")

        return job_id

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from the scheduler.

        Args:
            job_id: Job ID to remove

        Returns:
            True if removed, False if not found
        """
        try:
            self.scheduler.remove_job(job_id)
            return True
        except Exception as e:
            logger.warning(f"Failed to remove job '{job_id}': {e}")
            return False

    def get_jobs(self) -> List[Dict[str, Any]]:
        """
        Get list of all scheduled jobs.

        Returns:
            List of job information dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs

    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific job.

        Args:
            job_id: Job ID

        Returns:
            Job information dictionary or None if not found
        """
        job = self.scheduler.get_job(job_id)
        if not job:
            return None

        return {
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
            'pending': job.pending
        }

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            logger.info("Starting scheduler...")
            self.load_jobs_from_config()
            self.scheduler.start()
            logger.info("Scheduler started successfully")

            # Print loaded jobs
            jobs = self.get_jobs()
            if jobs:
                logger.info(f"Loaded {len(jobs)} job(s):")
                for job in jobs:
                    logger.info(f"  - {job['id']}: next run at {job['next_run']}")
            else:
                logger.warning("No jobs loaded")
        else:
            logger.warning("Scheduler is already running")

    def stop(self, wait: bool = True):
        """
        Stop the scheduler.

        Args:
            wait: If True, wait for running jobs to complete
        """
        if self.scheduler.running:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler stopped")
        else:
            logger.warning("Scheduler is not running")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running

    def print_jobs(self):
        """Print all scheduled jobs in a readable format."""
        jobs = self.get_jobs()

        if not jobs:
            print("No jobs scheduled")
            return

        print(f"\n{len(jobs)} scheduled job(s):\n")
        for job in jobs:
            print(f"  Job ID: {job['id']}")
            print(f"  Next Run: {job['next_run']}")
            print(f"  Trigger: {job['trigger']}")
            print()
