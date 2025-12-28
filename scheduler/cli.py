"""
Command-line interface for scheduler management.

Provides comprehensive CLI commands for:
- Starting/stopping scheduler
- Adding/removing/modifying jobs
- Viewing job status and logs
- Managing configuration

The scheduler is generic and command-based - it simply executes
shell commands on a schedule without knowing what they do.
"""

import argparse
import sys
import os
import logging
from datetime import datetime
from pathlib import Path
import time
import json

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from scheduler.service import SchedulerService, is_scheduler_running
from scheduler.config import SchedulerConfig, JobConfig, ScheduleConfig

logger = logging.getLogger(__name__)


def get_log_dir() -> Path:
    """Get the log directory from environment or default."""
    if os.environ.get('SCHEDULER_LOG_DIR'):
        return Path(os.environ['SCHEDULER_LOG_DIR']).expanduser()
    elif os.environ.get('EARNINGS_DATA_DIR'):
        return Path(os.environ['EARNINGS_DATA_DIR']).expanduser() / "logs"
    else:
        return Path.home() / ".earnings_data" / "logs"


def get_log_file() -> Path:
    """Get the scheduler log file path."""
    return get_log_dir() / "scheduler.log"


def setup_logging(log_file: str = None, verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


def cmd_start(args):
    """Start the scheduler."""
    setup_logging(
        log_file=args.log_file or str(get_log_file()),
        verbose=args.verbose
    )

    logger.info("Starting job scheduler...")

    try:
        service = SchedulerService(
            config_path=args.config,
            foreground=args.foreground,
            max_workers=args.workers
        )

        service.start()

        if args.foreground:
            logger.info("Running in foreground mode. Press Ctrl+C to stop.")
            try:
                # Keep running
                while True:
                    time.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Shutting down...")
                service.stop()
        else:
            logger.info("Scheduler is running in the background")
            logger.info("Use 'job-scheduler stop' to stop it")
            logger.info(f"Logs: {args.log_file}")

            # Write PID file
            pid_file = Path.home() / ".earnings_data" / "scheduler.pid"
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))

            # Keep running
            while service.is_running():
                time.sleep(60)

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        sys.exit(1)


def cmd_stop(args):
    """Stop the scheduler."""
    setup_logging(verbose=args.verbose)

    pid_file = Path.home() / ".earnings_data" / "scheduler.pid"

    if not pid_file.exists():
        logger.warning("Scheduler does not appear to be running (no PID file)")
        return

    try:
        import os
        import signal

        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        logger.info(f"Stopping scheduler (PID: {pid})...")
        os.kill(pid, signal.SIGTERM)

        # Wait for process to stop
        for _ in range(10):
            time.sleep(1)
            try:
                os.kill(pid, 0)  # Check if process exists
            except OSError:
                logger.info("Scheduler stopped successfully")
                pid_file.unlink()
                return

        logger.warning("Scheduler did not stop gracefully, sending SIGKILL")
        os.kill(pid, signal.SIGKILL)
        pid_file.unlink()

    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        sys.exit(1)


def cmd_status(args):
    """Show scheduler status."""
    setup_logging(verbose=args.verbose)

    try:
        # Check if scheduler is running via PID file
        running, pid = is_scheduler_running()
        
        print("\n=== Scheduler Status ===\n")
        print(f"Running: {running}")
        if running and pid:
            print(f"PID: {pid}")

        # Load config to show jobs from persisted store
        service = SchedulerService(config_path=args.config)
        jobs = service.get_persisted_jobs()
        print(f"Jobs in store: {len(jobs)}")

        if jobs:
            print("\nScheduled Jobs:")
            for job in jobs:
                print(f"\n  {job['id']}")
                print(f"    Next Run: {job['next_run']}")
                print(f"    Trigger: {job['trigger']}")

    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        sys.exit(1)


def cmd_list(args):
    """List all scheduled jobs."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig(args.config)

        print(f"\n=== Configured Jobs ({len(config.jobs)}) ===\n")

        for job in config.jobs:
            status = "✓" if job.enabled else "✗"
            print(f"{status} {job.name}")
            print(f"    Command: {job.command}")
            print(f"    Schedule: {job.schedule.type}", end="")

            if job.schedule.type == 'daily':
                print(f" at {job.schedule.time}")
            elif job.schedule.type == 'weekly':
                print(f" on {job.schedule.day} at {job.schedule.time}")
            elif job.schedule.type == 'interval':
                if job.schedule.hours:
                    print(f" every {job.schedule.hours} hour(s)")
                if job.schedule.minutes:
                    print(f" every {job.schedule.minutes} minute(s)")
            elif job.schedule.type == 'cron':
                print(f": {job.schedule.cron}")
            else:
                print()

            if job.description:
                print(f"    Description: {job.description}")
            if job.timeout != 3600:
                print(f"    Timeout: {job.timeout}s")
            print()

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        sys.exit(1)


def cmd_add(args):
    """Add a new scheduled job."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig(args.config)

        # Build schedule config
        if args.daily:
            schedule = ScheduleConfig(type='daily', time=args.time)
        elif args.weekly:
            schedule = ScheduleConfig(type='weekly', day=args.day, time=args.time)
        elif args.interval:
            schedule = ScheduleConfig(
                type='interval',
                hours=args.hours,
                minutes=args.minutes
            )
        elif args.cron:
            schedule = ScheduleConfig(type='cron', cron=args.cron)
        else:
            logger.error("Must specify schedule type: --daily, --weekly, --interval, or --cron")
            sys.exit(1)

        # Create job config
        job = JobConfig(
            name=args.name,
            command=args.command,
            enabled=True,
            schedule=schedule,
            timeout=args.timeout,
            description=args.description
        )

        config.add_job(job)
        config.save()

        logger.info(f"Added job '{args.name}'")
        logger.info(f"Command: {args.command}")
        logger.info("Restart scheduler for changes to take effect")

    except Exception as e:
        logger.error(f"Failed to add job: {e}")
        sys.exit(1)


def cmd_remove(args):
    """Remove a scheduled job."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig(args.config)

        if config.remove_job(args.name):
            config.save()
            logger.info(f"Removed job '{args.name}'")
            logger.info("Restart scheduler for changes to take effect")
        else:
            logger.error(f"Job '{args.name}' not found")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to remove job: {e}")
        sys.exit(1)


def cmd_enable(args):
    """Enable a job."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig(args.config)
        config.enable_job(args.name)
        config.save()

        logger.info(f"Enabled job '{args.name}'")
        logger.info("Restart scheduler for changes to take effect")

    except Exception as e:
        logger.error(f"Failed to enable job: {e}")
        sys.exit(1)


def cmd_disable(args):
    """Disable a job."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig(args.config)
        config.disable_job(args.name)
        config.save()

        logger.info(f"Disabled job '{args.name}'")
        logger.info("Restart scheduler for changes to take effect")

    except Exception as e:
        logger.error(f"Failed to disable job: {e}")
        sys.exit(1)


def cmd_run_once(args):
    """Run a one-time job."""
    setup_logging(verbose=args.verbose)

    try:
        # Parse run time for scheduled execution
        run_at = None
        if args.at:
            run_at = datetime.strptime(args.at, '%Y-%m-%d %H:%M')

        # If scheduling for later or background flag, use the scheduler
        if run_at or args.background:
            service = SchedulerService(config_path=args.config)
            job_id = service.add_one_time_job(
                command=args.command,
                run_at=run_at,
                timeout=args.timeout
            )
            logger.info(f"Queued one-time job '{job_id}'")
            logger.info(f"Command: {args.command}")
            if run_at:
                logger.info(f"Scheduled to run at: {run_at}")
                logger.info("Note: The scheduler service must be running for scheduled jobs to execute.")
                logger.info("Start it with: job-scheduler start --foreground")
            else:
                logger.info("Queued for background execution")
                logger.info("Note: The scheduler service must be running for background jobs to execute.")
        else:
            # Run immediately in the foreground (default behavior)
            from scheduler.jobs import CommandExecutor

            job_id = f"onetime_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Running job '{job_id}' now...")
            logger.info(f"Command: {args.command}")
            print()  # Blank line before command output

            executor = CommandExecutor()

            start_time = datetime.now()
            try:
                result = executor.execute_command(
                    args.command,
                    timeout=args.timeout,
                    stream_output=True  # Stream output in real-time
                )
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                print()  # Blank line after command output
                logger.info(f"Job '{job_id}' completed successfully in {duration:.1f}s")
            except Exception as job_error:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.error(f"Job '{job_id}' failed after {duration:.1f}s: {job_error}")
                sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to run job: {e}", exc_info=args.verbose)
        sys.exit(1)


def cmd_logs(args):
    """View scheduler logs."""
    log_file = get_log_file()
    
    if not log_file.exists():
        print(f"No log file found at: {log_file}")
        print("Logs are created when running jobs or starting the scheduler.")
        return
    
    try:
        # Read log file
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # Filter by job if specified
        if args.job:
            lines = [l for l in lines if args.job in l]
        
        # Filter by level if specified
        if args.level:
            level_upper = args.level.upper()
            lines = [l for l in lines if f'[{level_upper}]' in l]
        
        # Get last N lines (unless --all is specified)
        if not args.show_all and args.tail:
            lines = lines[-args.tail:]
        
        if not lines:
            print("No matching log entries found.")
            if args.job:
                print(f"  Filter: job contains '{args.job}'")
            if args.level:
                print(f"  Filter: level = {args.level.upper()}")
            return
        
        # Print logs
        for line in lines:
            # Color-code by level
            if args.color:
                if '[ERROR]' in line:
                    print(f"\033[91m{line.rstrip()}\033[0m")
                elif '[WARNING]' in line:
                    print(f"\033[93m{line.rstrip()}\033[0m")
                elif '[INFO]' in line:
                    print(f"\033[92m{line.rstrip()}\033[0m")
                else:
                    print(line.rstrip())
            else:
                print(line.rstrip())
        
        print(f"\n--- Showing {len(lines)} log entries from {log_file} ---")
        
    except Exception as e:
        print(f"Error reading logs: {e}")
        sys.exit(1)


def cmd_init(args):
    """Initialize scheduler configuration."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig()
        config.save()

        logger.info(f"Initialized scheduler configuration at: {config.config_path}")
        logger.info("Default job created: daily_transcripts (downloads at 2:00 AM)")

        # Create log directory
        log_dir = Path.home() / ".earnings_data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created log directory: {log_dir}")

    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)


def cmd_show_config(args):
    """Show current configuration."""
    setup_logging(verbose=args.verbose)

    try:
        config = SchedulerConfig(args.config)

        print(f"\nConfiguration file: {config.config_path}")
        print(f"\nJobs: {len(config.jobs)}")
        print(f"Logging level: {config.logging.level}")
        print(f"Log file: {config.logging.file}")
        print(f"Max retries: {config.error_handling.max_retries}")
        print(f"Retry delay: {config.error_handling.retry_delay_minutes} minutes")

    except Exception as e:
        logger.error(f"Failed to show config: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    import os  # Import here to avoid issues with module-level code

    parser = argparse.ArgumentParser(
        description="Job Scheduler - Run any command on a schedule with dynamic job queues",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-c', '--config',
        type=str,
        help='Path to scheduler configuration file'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Start command
    start_parser = subparsers.add_parser('start', help='Start the scheduler')
    start_parser.add_argument(
        '--foreground',
        action='store_true',
        help='Run in foreground (blocking mode)'
    )
    start_parser.add_argument(
        '--workers',
        type=int,
        default=5,
        help='Maximum concurrent workers (default: 5)'
    )
    start_parser.add_argument(
        '--log-file',
        type=str,
        help='Log file path'
    )
    start_parser.set_defaults(func=cmd_start)

    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop the scheduler')
    stop_parser.set_defaults(func=cmd_stop)

    # Status command
    status_parser = subparsers.add_parser('status', help='Show scheduler status')
    status_parser.set_defaults(func=cmd_status)

    # List command
    list_parser = subparsers.add_parser('list', help='List all jobs')
    list_parser.set_defaults(func=cmd_list)

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new scheduled job')
    add_parser.add_argument('name', help='Job name')
    add_parser.add_argument(
        '--command', '-c',
        required=True,
        help='Shell command to execute (e.g., "earnings-download-transcripts --all")'
    )

    # Schedule type (mutually exclusive)
    schedule_group = add_parser.add_mutually_exclusive_group(required=True)
    schedule_group.add_argument('--daily', action='store_true', help='Daily schedule')
    schedule_group.add_argument('--weekly', action='store_true', help='Weekly schedule')
    schedule_group.add_argument('--interval', action='store_true', help='Interval schedule')
    schedule_group.add_argument('--cron', type=str, help='Cron expression')

    # Schedule parameters
    add_parser.add_argument('--time', type=str, help='Time (HH:MM) for daily/weekly')
    add_parser.add_argument('--day', type=str, help='Day of week for weekly')
    add_parser.add_argument('--hours', type=int, help='Interval in hours')
    add_parser.add_argument('--minutes', type=int, help='Interval in minutes')

    # Job options
    add_parser.add_argument('--timeout', type=int, default=3600,
                            help='Command timeout in seconds (default: 3600)')
    add_parser.add_argument('--description', type=str, help='Human-readable description')
    add_parser.set_defaults(func=cmd_add)

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a scheduled job')
    remove_parser.add_argument('name', help='Job name to remove')
    remove_parser.set_defaults(func=cmd_remove)

    # Enable command
    enable_parser = subparsers.add_parser('enable', help='Enable a job')
    enable_parser.add_argument('name', help='Job name to enable')
    enable_parser.set_defaults(func=cmd_enable)

    # Disable command
    disable_parser = subparsers.add_parser('disable', help='Disable a job')
    disable_parser.add_argument('name', help='Job name to disable')
    disable_parser.set_defaults(func=cmd_disable)

    # Run-once command
    run_once_parser = subparsers.add_parser('run-once', help='Run a one-time command immediately')
    run_once_parser.add_argument(
        '--command', '-c',
        required=True,
        help='Shell command to execute'
    )
    run_once_parser.add_argument('--timeout', type=int, default=3600,
                                  help='Command timeout in seconds (default: 3600)')
    run_once_parser.add_argument('--at', type=str, help='Schedule to run at specific time (YYYY-MM-DD HH:MM)')
    run_once_parser.add_argument('--background', action='store_true',
                                  help='Queue for background execution (requires scheduler running)')
    run_once_parser.set_defaults(func=cmd_run_once)

    # Logs command
    logs_parser = subparsers.add_parser('logs', help='View scheduler logs')
    logs_parser.add_argument('--job', type=str, help='Filter logs by job name/ID')
    logs_parser.add_argument('--level', type=str, choices=['info', 'warning', 'error', 'debug'],
                             help='Filter by log level')
    logs_parser.add_argument('--tail', '-n', type=int, default=50, help='Show last N lines (default: 50)')
    logs_parser.add_argument('--all', '-a', dest='show_all', action='store_true', 
                             help='Show all logs (not just last N)')
    logs_parser.add_argument('--color', '-c', action='store_true', help='Colorize output')
    logs_parser.set_defaults(func=cmd_logs)

    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize scheduler configuration')
    init_parser.set_defaults(func=cmd_init)

    # Show config command
    show_config_parser = subparsers.add_parser('show-config', help='Show configuration')
    show_config_parser.set_defaults(func=cmd_show_config)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
