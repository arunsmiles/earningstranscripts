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

from scheduler.service import SchedulerService, is_scheduler_running, get_scheduler_info
from scheduler.config import SchedulerConfig, JobConfig, ScheduleConfig
from scheduler.jobs import get_history_store, CommandExecutor, HistoryStore

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
        # Get scheduler info (includes running status)
        scheduler_info = get_scheduler_info()
        running, pid = is_scheduler_running()
        
        print("\n┌─────────────────────────────────────────────────────────────────┐")
        print("│                      SCHEDULER STATUS                           │")
        print("└─────────────────────────────────────────────────────────────────┘\n")
        
        if running:
            print(f"  Status:     \033[92m● Running\033[0m")
            print(f"  PID:        {pid}")
            
            if scheduler_info:
                if scheduler_info.get('started_at'):
                    print(f"  Started:    {scheduler_info.get('started_at', 'N/A')}")
                if scheduler_info.get('config_path'):
                    print(f"  Config:     {scheduler_info.get('config_path', 'N/A')}")
                print(f"  Data Dir:   {scheduler_info.get('data_dir', 'N/A')}")
                print(f"  Job Store:  {scheduler_info.get('job_store_path', 'N/A')}")
                print(f"  Log Dir:    {scheduler_info.get('log_dir', 'N/A')}")
        else:
            print(f"  Status:     \033[91m○ Not Running\033[0m")
            print("\n  Start the scheduler with: job-scheduler start --foreground")
            return

        # Load jobs from persisted store (using scheduler's paths)
        job_store_path = scheduler_info.get('job_store_path') if scheduler_info else None
        service = SchedulerService(config_path=args.config, job_store_path=job_store_path)
        jobs = service.get_persisted_jobs()
        
        print(f"\n  Active Jobs: {len(jobs)}")

        if jobs:
            print("\n  ┌" + "─" * 50 + "┐")
            print("  │ Scheduled Jobs" + " " * 35 + "│")
            print("  ├" + "─" * 50 + "┤")
            for job in jobs:
                job_id = job['id'][:30]
                next_run = job['next_run'][:19] if job['next_run'] else 'N/A'
                print(f"  │  {job_id:<28} Next: {next_run:<19} │")
            print("  └" + "─" * 50 + "┘")
        
        print()

    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def cmd_list(args):
    """List all scheduled jobs from the running scheduler."""
    setup_logging(verbose=args.verbose)

    try:
        # Check if scheduler is running and get its info
        scheduler_info = get_scheduler_info()
        running, pid = is_scheduler_running()
        
        if not running:
            print("\n\033[93mScheduler is not running.\033[0m")
            print("Showing jobs from configuration file instead.\n")
            # Fall back to config file
            config = SchedulerConfig(args.config)
            _print_config_jobs(config)
            return
        
        # Use the running scheduler's job store
        job_store_path = scheduler_info.get('job_store_path') if scheduler_info else None
        config_path = scheduler_info.get('config_path') if scheduler_info else args.config
        
        service = SchedulerService(config_path=config_path, job_store_path=job_store_path)
        jobs = service.get_persisted_jobs()
        
        print(f"\n┌─────────────────────────────────────────────────────────────────┐")
        print(f"│                    ACTIVE SCHEDULED JOBS                        │")
        print(f"└─────────────────────────────────────────────────────────────────┘")
        print(f"\n  Scheduler PID: {pid}")
        if scheduler_info and scheduler_info.get('config_path'):
            print(f"  Config: {scheduler_info.get('config_path')}")
        print(f"  Total Jobs: {len(jobs)}\n")

        if not jobs:
            print("  No jobs are currently scheduled.")
            print()
            return
        
        # Also load config for job details (command, description)
        config = None
        if config_path:
            try:
                config = SchedulerConfig(config_path)
            except:
                pass
        
        for job in jobs:
            job_id = job['id']
            next_run = job['next_run']
            trigger = job['trigger']
            
            # Try to get job details from config
            job_config = None
            if config:
                for j in config.jobs:
                    if j.name == job_id:
                        job_config = j
                        break
            
            print(f"  \033[1m{job_id}\033[0m")
            print(f"    Next Run: {next_run}")
            print(f"    Trigger:  {trigger}")
            if job_config:
                print(f"    Command:  {job_config.command}")
                if job_config.description:
                    print(f"    Description: {job_config.description}")
            print()

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _print_config_jobs(config: SchedulerConfig):
    """Helper to print jobs from a config file."""
    print(f"=== Configured Jobs ({len(config.jobs)}) ===\n")

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
            import uuid
            job_id = f"onetime_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            run_id = str(uuid.uuid4())[:8]
            logger.info(f"Running job '{job_id}' now...")
            logger.info(f"Command: {args.command}")
            print()  # Blank line before command output

            executor = CommandExecutor()
            history_store = get_history_store()

            start_time = datetime.now()
            
            # Record run start in history
            history_record = {
                'job_name': job_id,
                'run_id': run_id,
                'command': args.command,
                'start_time': start_time.isoformat(),
                'end_time': None,
                'elapsed_seconds': None,
                'status': 'running',
                'exit_code': None,
                'error': None,
                'attempts': 1
            }
            history_store.add_run(history_record)
            
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
                
                # Update history with success
                history_store.update_run(run_id, {
                    'end_time': end_time.isoformat(),
                    'elapsed_seconds': round(duration, 2),
                    'status': 'success',
                    'exit_code': result.get('returncode', 0)
                })
            except Exception as job_error:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.error(f"Job '{job_id}' failed after {duration:.1f}s: {job_error}")
                
                # Update history with failure
                history_store.update_run(run_id, {
                    'end_time': end_time.isoformat(),
                    'elapsed_seconds': round(duration, 2),
                    'status': 'failed',
                    'error': str(job_error)
                })
                sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to run job: {e}", exc_info=args.verbose)
        sys.exit(1)


def cmd_logs(args):
    """View scheduler logs from the running scheduler."""
    # Try to get log path from running scheduler
    scheduler_info = get_scheduler_info()
    
    if scheduler_info and scheduler_info.get('log_dir'):
        log_file = Path(scheduler_info['log_dir']) / "scheduler.log"
    else:
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


def cmd_history(args):
    """Show job run history from the running scheduler."""
    try:
        # Try to get history file path from running scheduler
        scheduler_info = get_scheduler_info()
        
        if scheduler_info and scheduler_info.get('history_file'):
            history_file = Path(scheduler_info['history_file'])
            history_store = HistoryStore(history_file=history_file)
        else:
            history_store = get_history_store()
        
        # Get history with filters
        history = history_store.get_history(
            job_name=args.job,
            status=args.status,
            limit=args.limit if not args.show_all else None
        )
        
        if not history:
            print("\nNo job run history found.")
            if args.job:
                print(f"  Filter: job = '{args.job}'")
            if args.status:
                print(f"  Filter: status = '{args.status}'")
            return
        
        # Determine output format
        if args.json:
            print(json.dumps(history, indent=2))
            return
        
        # Prepare table data
        rows = []
        for record in history:
            job_name = record.get('job_name', 'unknown')
            run_id = record.get('run_id', 'N/A')
            
            # Format start time
            start_time_str = record.get('start_time', '')
            if start_time_str:
                try:
                    start_dt = datetime.fromisoformat(start_time_str)
                    start_time = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    start_time = start_time_str[:19]
            else:
                start_time = 'N/A'
            
            # Format end time
            end_time_str = record.get('end_time', '')
            if end_time_str:
                try:
                    end_dt = datetime.fromisoformat(end_time_str)
                    end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    end_time = end_time_str[:19]
            else:
                end_time = 'running...'
            
            # Format elapsed time
            elapsed = record.get('elapsed_seconds')
            if elapsed is not None:
                if elapsed >= 3600:
                    elapsed_str = f"{elapsed/3600:.1f}h"
                elif elapsed >= 60:
                    elapsed_str = f"{elapsed/60:.1f}m"
                else:
                    elapsed_str = f"{elapsed:.1f}s"
            else:
                elapsed_str = '-'
            
            status = record.get('status', 'unknown')
            error = record.get('error', '') if args.verbose and status == 'failed' else None
            
            rows.append({
                'job_name': job_name,
                'run_id': run_id,
                'start_time': start_time,
                'end_time': end_time,
                'elapsed': elapsed_str,
                'status': status,
                'error': error
            })
        
        # Calculate column widths
        headers = ['Job Name', 'Run ID', 'Start Time', 'End Time', 'Elapsed', 'Status']
        col_widths = [
            max(len(headers[0]), max(len(r['job_name']) for r in rows)),
            max(len(headers[1]), max(len(r['run_id']) for r in rows)),
            max(len(headers[2]), 19),  # datetime width
            max(len(headers[3]), 19),
            max(len(headers[4]), max(len(r['elapsed']) for r in rows)),
            max(len(headers[5]), max(len(r['status']) for r in rows)),
        ]
        
        # Build table
        def make_row(cells, widths):
            return "│ " + " │ ".join(cell.ljust(w) for cell, w in zip(cells, widths)) + " │"
        
        def make_separator(widths, left, mid, right, fill='─'):
            return left + mid.join(fill * (w + 2) for w in widths) + right
        
        # Print table
        print()
        print(make_separator(col_widths, '┌', '┬', '┐'))
        print(make_row(headers, col_widths))
        print(make_separator(col_widths, '├', '┼', '┤'))
        
        for row in rows:
            status = row['status']
            if args.color:
                if status == 'success':
                    status_cell = f"\033[92m{status}\033[0m" + ' ' * (col_widths[5] - len(status))
                elif status == 'failed':
                    status_cell = f"\033[91m{status}\033[0m" + ' ' * (col_widths[5] - len(status))
                elif status == 'running':
                    status_cell = f"\033[93m{status}\033[0m" + ' ' * (col_widths[5] - len(status))
                else:
                    status_cell = status.ljust(col_widths[5])
                
                # Build row manually for colored status
                cells = [
                    row['job_name'].ljust(col_widths[0]),
                    row['run_id'].ljust(col_widths[1]),
                    row['start_time'].ljust(col_widths[2]),
                    row['end_time'].ljust(col_widths[3]),
                    row['elapsed'].ljust(col_widths[4]),
                    status_cell
                ]
                print("│ " + " │ ".join(cells) + " │")
            else:
                cells = [row['job_name'], row['run_id'], row['start_time'], 
                         row['end_time'], row['elapsed'], row['status']]
                print(make_row(cells, col_widths))
            
            # Show error if verbose
            if row['error']:
                error_msg = row['error'][:80]
                print(f"│   └─ Error: {error_msg}")
        
        print(make_separator(col_widths, '└', '┴', '┘'))
        
        print(f"\nShowing {len(history)} run(s)")
        print(f"History file: {history_store.history_file}")
        print(f"\nTo view logs for a specific run: job-scheduler logs --job <job_name>")
        
    except Exception as e:
        print(f"Error reading history: {e}")
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

    # History command
    history_parser = subparsers.add_parser('history', help='View job run history')
    history_parser.add_argument('--job', '-j', type=str, help='Filter by job name')
    history_parser.add_argument('--status', '-s', type=str, 
                                choices=['success', 'failed', 'running'],
                                help='Filter by status')
    history_parser.add_argument('--limit', '-n', type=int, default=20,
                                help='Maximum number of entries to show (default: 20)')
    history_parser.add_argument('--all', '-a', dest='show_all', action='store_true',
                                help='Show all history entries')
    history_parser.add_argument('--json', action='store_true',
                                help='Output in JSON format')
    history_parser.add_argument('--color', '-c', action='store_true',
                                help='Colorize status output')
    history_parser.add_argument('--verbose', '-v', action='store_true',
                                help='Show additional details (error messages)')
    history_parser.set_defaults(func=cmd_history)

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
