"""
Core scheduler service using APScheduler.

Provides a production-ready scheduling system with:
- Persistent job storage (SQLite)
- Dynamic job management
- Concurrent execution
- Job event logging
- PID file for status tracking

The scheduler is generic and command-based - it simply executes
shell commands on a schedule without knowing what they do.
"""

import atexit
import logging
import os
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
from scheduler.jobs import CommandExecutor, execute_scheduled_command, JobExecutionError

logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    """Get the data directory for scheduler files."""
    data_dir = os.environ.get('EARNINGS_DATA_DIR')
    if data_dir:
        return Path(data_dir).expanduser()
    return Path.home() / ".earnings_data"


def _get_pid_file_path() -> Path:
    """Get the path to the scheduler PID file."""
    # Check SCHEDULER_PID_FILE first
    pid_path = os.environ.get('SCHEDULER_PID_FILE')
    if pid_path:
        return Path(pid_path)
    
    return _get_data_dir() / "scheduler.pid"


def _get_info_file_path() -> Path:
    """Get the path to the scheduler info file."""
    return _get_data_dir() / "scheduler_info.json"


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks
        return True
    except OSError:
        return False


def get_scheduler_info() -> Optional[Dict[str, Any]]:
    """
    Get information about the running scheduler.
    
    Returns:
        Dict with scheduler info or None if not running/no info file.
    """
    import json
    
    running, pid = is_scheduler_running()
    if not running:
        return None
    
    info_file = _get_info_file_path()
    if not info_file.exists():
        # Return minimal info if no info file but scheduler is running
        return {
            'pid': pid,
            'running': True,
            'data_dir': str(_get_data_dir()),
        }
    
    try:
        with open(info_file, 'r') as f:
            info = json.load(f)
        info['running'] = True
        info['pid'] = pid
        return info
    except (json.JSONDecodeError, OSError):
        return {'pid': pid, 'running': True, 'data_dir': str(_get_data_dir())}


def is_scheduler_running() -> tuple[bool, Optional[int]]:
    """
    Check if the scheduler is running by reading the PID file.
    
    Returns:
        Tuple of (is_running, pid). If not running, pid is None.
    """
    pid_file = _get_pid_file_path()
    
    if not pid_file.exists():
        return False, None
    
    try:
        pid = int(pid_file.read_text().strip())
        if _is_process_running(pid):
            return True, pid
        else:
            # Stale PID file, clean it up
            pid_file.unlink()
            return False, None
    except (ValueError, OSError):
        return False, None


class SchedulerService:
    """
    Main scheduler service managing job execution.

    Uses APScheduler with SQLite job store for persistence.
    Executes generic shell commands on a schedule.
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
        self.executor = CommandExecutor()

        # Setup job store - check environment variables for path
        if not job_store_path:
            job_store_path = os.environ.get('SCHEDULER_JOB_STORE_PATH')
            if not job_store_path:
                # Fall back to EARNINGS_DATA_DIR/scheduler_jobs.db
                data_dir = os.environ.get('EARNINGS_DATA_DIR')
                if data_dir:
                    job_store_path = str(Path(data_dir) / "scheduler_jobs.db")
                else:
                    # Final fallback to home directory
                    job_store_path = str(Path.home() / ".earnings_data" / "scheduler_jobs.db")

        # Store the path for later use
        self.job_store_path = job_store_path

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
        # Job arguments for the module-level function
        job_kwargs = {
            'command': job_config.command,
            'job_name': job_config.name,
            'max_retries': self.config.error_handling.max_retries,
            'retry_delay_minutes': self.config.error_handling.retry_delay_minutes,
            'timeout': job_config.timeout
        }

        # Add to scheduler based on schedule type
        schedule = job_config.schedule

        if schedule.type == 'daily':
            self.scheduler.add_job(
                execute_scheduled_command,
                'cron',
                hour=int(schedule.time.split(':')[0]),
                minute=int(schedule.time.split(':')[1]),
                id=job_config.name,
                replace_existing=True,
                kwargs=job_kwargs
            )

        elif schedule.type == 'weekly':
            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            self.scheduler.add_job(
                execute_scheduled_command,
                'cron',
                day_of_week=day_map.get(schedule.day.lower(), 0),
                hour=int(schedule.time.split(':')[0]),
                minute=int(schedule.time.split(':')[1]),
                id=job_config.name,
                replace_existing=True,
                kwargs=job_kwargs
            )

        elif schedule.type == 'interval':
            interval_kwargs = {}
            if schedule.hours:
                interval_kwargs['hours'] = schedule.hours
            if schedule.minutes:
                interval_kwargs['minutes'] = schedule.minutes

            self.scheduler.add_job(
                execute_scheduled_command,
                'interval',
                **interval_kwargs,
                id=job_config.name,
                replace_existing=True,
                kwargs=job_kwargs
            )

        elif schedule.type == 'cron':
            # Parse cron expression (assumes standard cron format)
            self.scheduler.add_job(
                execute_scheduled_command,
                'cron',
                **self._parse_cron_expression(schedule.cron),
                id=job_config.name,
                replace_existing=True,
                kwargs=job_kwargs
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
        command: str,
        run_at: Optional[datetime] = None,
        job_id: Optional[str] = None,
        timeout: int = 3600
    ) -> str:
        """
        Add a one-time job to run immediately or at a specific time.

        Args:
            command: Shell command to execute
            run_at: When to run the job (None = immediately)
            job_id: Optional job ID (auto-generated if not provided)
            timeout: Command timeout in seconds

        Returns:
            Job ID
        """
        if not job_id:
            job_id = f"onetime_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Job arguments for the module-level function
        job_kwargs = {
            'command': command,
            'job_name': job_id,
            'max_retries': self.config.error_handling.max_retries,
            'retry_delay_minutes': self.config.error_handling.retry_delay_minutes,
            'timeout': timeout
        }

        if run_at:
            self.scheduler.add_job(
                execute_scheduled_command,
                'date',
                run_date=run_at,
                id=job_id,
                replace_existing=True,
                kwargs=job_kwargs
            )
            logger.info(f"Scheduled one-time job '{job_id}' for {run_at}")
        else:
            # Run immediately
            self.scheduler.add_job(
                execute_scheduled_command,
                'date',
                run_date=datetime.now(),
                id=job_id,
                replace_existing=True,
                kwargs=job_kwargs
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

    def get_persisted_jobs(self) -> List[Dict[str, Any]]:
        """
        Get list of jobs from the persisted SQLite store.
        
        This is useful for checking jobs when the scheduler isn't running
        in the current process.
        
        Returns:
            List of job information dictionaries
        """
        import sqlite3
        import pickle
        
        jobs = []
        try:
            conn = sqlite3.connect(self.job_store_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, next_run_time, job_state FROM apscheduler_jobs")
            
            for row in cursor.fetchall():
                job_id = row[0]
                next_run_ts = row[1]
                # Convert timestamp to ISO format
                if next_run_ts:
                    next_run = datetime.fromtimestamp(next_run_ts).isoformat()
                else:
                    next_run = None
                # job_state is pickled, try to extract trigger info
                try:
                    job_state = pickle.loads(row[2])
                    trigger = str(job_state.get('trigger', 'unknown'))
                except:
                    trigger = 'unknown'
                
                jobs.append({
                    'id': job_id,
                    'next_run': next_run,
                    'trigger': trigger
                })
            
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to read persisted jobs: {e}")
        
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
        # Check if another scheduler is already running
        running, pid = is_scheduler_running()
        if running:
            logger.warning(f"Scheduler is already running (PID: {pid})")
            return
        
        if not self.scheduler.running:
            logger.info("Starting scheduler...")
            self.load_jobs_from_config()
            self.scheduler.start()
            
            # Write PID file
            self._write_pid_file()
            
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

    def _write_pid_file(self):
        """Write the current process PID and scheduler info files."""
        import json
        
        # Write PID file
        pid_file = _get_pid_file_path()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))
        logger.debug(f"Wrote PID file: {pid_file}")
        
        # Write scheduler info file with runtime configuration
        info_file = _get_info_file_path()
        scheduler_info = {
            'pid': os.getpid(),
            'started_at': datetime.now().isoformat(),
            'config_path': str(self.config.config_path) if self.config.config_path else None,
            'job_store_path': self.job_store_path,
            'data_dir': str(_get_data_dir()),
            'log_dir': str(_get_data_dir() / "logs"),
            'history_file': str(_get_data_dir() / "scheduler_history.json"),
            'working_directory': os.getcwd(),
        }
        
        try:
            with open(info_file, 'w') as f:
                json.dump(scheduler_info, f, indent=2)
            logger.debug(f"Wrote scheduler info file: {info_file}")
        except OSError as e:
            logger.warning(f"Failed to write scheduler info file: {e}")
        
        # Register cleanup on exit
        atexit.register(self._remove_pid_file)
    
    def _remove_pid_file(self):
        """Remove the PID and info files."""
        pid_file = _get_pid_file_path()
        info_file = _get_info_file_path()
        
        try:
            if pid_file.exists():
                pid_file.unlink()
                logger.debug(f"Removed PID file: {pid_file}")
        except OSError:
            pass
        
        try:
            if info_file.exists():
                info_file.unlink()
                logger.debug(f"Removed scheduler info file: {info_file}")
        except OSError:
            pass

    def stop(self, wait: bool = True):
        """
        Stop the scheduler.

        Args:
            wait: If True, wait for running jobs to complete
        """
        if self.scheduler.running:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown(wait=wait)
            self._remove_pid_file()
            logger.info("Scheduler stopped")
        else:
            logger.warning("Scheduler is not running")

    def is_running(self) -> bool:
        """Check if scheduler is running (either this instance or another process)."""
        # Check this instance first
        if self.scheduler.running:
            return True
        # Check if another process is running
        running, _ = is_scheduler_running()
        return running

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
