"""
Generic command execution for scheduled jobs.

Executes shell commands with error handling, timeout, and logging.
The scheduler is completely decoupled from specific tools - it simply
runs whatever command you specify.
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def _get_history_file_path() -> Path:
    """Get the path to the job history file."""
    # Check SCHEDULER_HISTORY_FILE first
    history_path = os.environ.get('SCHEDULER_HISTORY_FILE')
    if history_path:
        return Path(history_path)
    
    # Fall back to EARNINGS_DATA_DIR
    data_dir = os.environ.get('EARNINGS_DATA_DIR')
    if data_dir:
        return Path(data_dir) / "scheduler_history.json"
    
    # Final fallback
    return Path.home() / ".earnings_data" / "scheduler_history.json"


class HistoryStore:
    """
    Persists job run history to a JSON file.
    
    Each run record contains:
    - job_name: Name of the job
    - run_id: Unique run identifier
    - start_time: When the run started (ISO format)
    - end_time: When the run ended (ISO format)
    - elapsed_seconds: Duration in seconds
    - status: 'success', 'failed', or 'running'
    - exit_code: Process exit code (if completed)
    - error: Error message (if failed)
    - command: The command that was executed
    """
    
    def __init__(self, history_file: Path = None, max_entries: int = 1000):
        """
        Initialize history store.
        
        Args:
            history_file: Path to history JSON file (uses default if not specified)
            max_entries: Maximum number of history entries to keep
        """
        self.history_file = history_file or _get_history_file_path()
        self.max_entries = max_entries
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Ensure the history file and its parent directory exist."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_file.exists():
            self._write_history([])
    
    def _read_history(self) -> List[Dict[str, Any]]:
        """Read history from file."""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _write_history(self, history: List[Dict[str, Any]]):
        """Write history to file."""
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=2, default=str)
    
    def add_run(self, record: Dict[str, Any]):
        """
        Add a run record to history.
        
        Args:
            record: Run record dictionary
        """
        history = self._read_history()
        history.append(record)
        
        # Trim to max entries (keep most recent)
        if len(history) > self.max_entries:
            history = history[-self.max_entries:]
        
        self._write_history(history)
    
    def update_run(self, run_id: str, updates: Dict[str, Any]):
        """
        Update an existing run record.
        
        Args:
            run_id: The run ID to update
            updates: Dictionary of fields to update
        """
        history = self._read_history()
        for record in history:
            if record.get('run_id') == run_id:
                record.update(updates)
                break
        self._write_history(history)
    
    def get_history(
        self,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get run history with optional filters.
        
        Args:
            job_name: Filter by job name
            status: Filter by status ('success', 'failed', 'running')
            limit: Maximum number of entries to return
        
        Returns:
            List of run records (most recent first)
        """
        history = self._read_history()
        
        # Apply filters
        if job_name:
            history = [r for r in history if r.get('job_name') == job_name]
        if status:
            history = [r for r in history if r.get('status') == status]
        
        # Sort by start_time descending (most recent first)
        history.sort(key=lambda r: r.get('start_time', ''), reverse=True)
        
        # Apply limit
        if limit:
            history = history[:limit]
        
        return history
    
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific run by ID.
        
        Args:
            run_id: The run ID to find
        
        Returns:
            Run record or None if not found
        """
        history = self._read_history()
        for record in history:
            if record.get('run_id') == run_id:
                return record
        return None
    
    def clear_history(self, job_name: Optional[str] = None):
        """
        Clear history, optionally for a specific job.
        
        Args:
            job_name: If specified, only clear history for this job
        """
        if job_name:
            history = self._read_history()
            history = [r for r in history if r.get('job_name') != job_name]
            self._write_history(history)
        else:
            self._write_history([])


# Global history store instance
_history_store: Optional[HistoryStore] = None


def get_history_store() -> HistoryStore:
    """Get or create the global history store instance."""
    global _history_store
    if _history_store is None:
        _history_store = HistoryStore()
    return _history_store


class JobExecutionError(Exception):
    """Raised when job execution fails."""
    pass


class CommandExecutor:
    """
    Executes shell commands with retry logic and statistics tracking.

    This is a generic executor that can run any command - it knows nothing
    about transcripts, SEC filings, or any specific tool.
    """

    def __init__(self):
        """Initialize command executor."""
        self.job_stats = {}  # Track job execution statistics

    def execute_command(
        self,
        command: str,
        timeout: Optional[int] = 3600,
        working_dir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        stream_output: bool = False,
        job_name: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds (default: 1 hour)
            working_dir: Working directory for command execution
            env: Additional environment variables
            stream_output: If True, stream output to console in real-time
            job_name: Name of the job (for logging)
            run_id: Unique run identifier (for logging)

        Returns:
            Dict with stdout, stderr, returncode

        Raises:
            JobExecutionError: If command fails (non-zero exit code)
        """
        # Create log prefix with job context
        log_prefix = ""
        if job_name and run_id:
            log_prefix = f"[{job_name}:{run_id}] "
        elif job_name:
            log_prefix = f"[{job_name}] "
        
        logger.info(f"{log_prefix}Executing command: {command}")

        try:
            if stream_output:
                # Stream output in real-time (for interactive/foreground use)
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=working_dir,
                    env=env
                )

                stdout_lines = []
                try:
                    for line in process.stdout:
                        print(line, end='')  # Print in real-time
                        stdout_lines.append(line)
                except Exception:
                    pass

                process.wait(timeout=timeout)
                stdout = ''.join(stdout_lines)

                if process.returncode != 0:
                    raise JobExecutionError(
                        f"Command failed with exit code {process.returncode}"
                    )

                return {
                    'stdout': stdout,
                    'stderr': '',
                    'returncode': process.returncode
                }
            else:
                # Stream output with logging (for scheduled jobs)
                # This allows seeing output in real-time in logs
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=working_dir,
                    env=env
                )

                stdout_lines = []
                stderr_lines = []
                
                # Read stdout and stderr in real-time using threads
                import threading
                import queue
                
                def read_stream(stream, output_list, log_func, prefix=""):
                    for line in stream:
                        line = line.rstrip('\n')
                        output_list.append(line)
                        log_func(f"{log_prefix}{prefix}{line}")
                
                # Start threads to read both streams
                stdout_thread = threading.Thread(
                    target=read_stream,
                    args=(process.stdout, stdout_lines, logger.info, "")
                )
                stderr_thread = threading.Thread(
                    target=read_stream,
                    args=(process.stderr, stderr_lines, logger.info, "")
                )
                
                stdout_thread.start()
                stderr_thread.start()
                
                # Wait for process with timeout
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    raise
                
                stdout_thread.join()
                stderr_thread.join()
                
                stdout = '\n'.join(stdout_lines)
                stderr = '\n'.join(stderr_lines)

                if process.returncode != 0:
                    raise JobExecutionError(
                        f"Command failed with exit code {process.returncode}: {stderr}"
                    )

                return {
                    'stdout': stdout,
                    'stderr': stderr,
                    'returncode': process.returncode
                }

        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out after {timeout}s: {command}")
            raise JobExecutionError(f"Command timed out after {timeout}s") from e

        except JobExecutionError:
            raise

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise JobExecutionError(f"Command execution failed: {e}") from e

    def execute_with_retry(
        self,
        command: str,
        job_name: str,
        max_retries: int = 3,
        retry_delay_minutes: int = 15,
        timeout: Optional[int] = 3600,
        record_history: bool = True
    ) -> Dict[str, Any]:
        """
        Execute command with retry logic and statistics tracking.

        Args:
            command: Shell command to execute
            job_name: Name of the job for logging
            max_retries: Maximum number of retry attempts
            retry_delay_minutes: Delay between retries in minutes
            timeout: Command timeout in seconds
            record_history: Whether to record run in history

        Returns:
            Dict with execution statistics

        Raises:
            JobExecutionError: If command fails after all retries
        """
        import uuid
        
        # Generate unique run ID (short form for readability)
        run_id = str(uuid.uuid4())[:8]
        log_prefix = f"[{job_name}:{run_id}]"
        
        start_time = datetime.now()
        attempt = 0
        last_error = None
        exit_code = None
        
        logger.info(f"{log_prefix} Starting job run")
        
        # Record run start in history
        if record_history:
            history_store = get_history_store()
            history_record = {
                'job_name': job_name,
                'run_id': run_id,
                'command': command,
                'start_time': start_time.isoformat(),
                'end_time': None,
                'elapsed_seconds': None,
                'status': 'running',
                'exit_code': None,
                'error': None,
                'attempts': 0
            }
            history_store.add_run(history_record)

        while attempt < max_retries:
            try:
                logger.info(f"{log_prefix} Attempt {attempt + 1}/{max_retries}")

                # Execute command with job context
                result = self.execute_command(
                    command, 
                    timeout=timeout,
                    job_name=job_name,
                    run_id=run_id
                )

                # Success
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                exit_code = result['returncode']
                
                stats = {
                    'job_name': job_name,
                    'run_id': run_id,
                    'command': command,
                    'status': 'success',
                    'duration_seconds': duration,
                    'attempts': attempt + 1,
                    'returncode': exit_code,
                    'timestamp': end_time.isoformat()
                }

                self.job_stats[job_name] = stats
                logger.info(f"{log_prefix} Completed successfully in {duration:.2f}s")
                
                # Update history with success
                if record_history:
                    history_store.update_run(run_id, {
                        'end_time': end_time.isoformat(),
                        'elapsed_seconds': round(duration, 2),
                        'status': 'success',
                        'exit_code': exit_code,
                        'attempts': attempt + 1
                    })
                
                return stats

            except JobExecutionError as e:
                last_error = e
                attempt += 1

                if attempt < max_retries:
                    delay_seconds = retry_delay_minutes * 60
                    logger.warning(
                        f"{log_prefix} Failed (attempt {attempt}/{max_retries}): {e}"
                    )
                    logger.info(f"{log_prefix} Retrying in {retry_delay_minutes} minutes...")
                    time.sleep(delay_seconds)
                else:
                    logger.error(f"{log_prefix} Failed after {max_retries} attempts")

        # All retries exhausted
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        stats = {
            'job_name': job_name,
            'run_id': run_id,
            'command': command,
            'status': 'failed',
            'duration_seconds': duration,
            'attempts': max_retries,
            'error': str(last_error),
            'timestamp': end_time.isoformat()
        }

        self.job_stats[job_name] = stats
        
        # Update history with failure
        if record_history:
            history_store.update_run(run_id, {
                'end_time': end_time.isoformat(),
                'elapsed_seconds': round(duration, 2),
                'status': 'failed',
                'attempts': max_retries,
                'error': str(last_error)
            })
        
        raise JobExecutionError(
            f"{log_prefix} Failed after {max_retries} attempts: {last_error}"
        ) from last_error

    def get_job_stats(self, job_name: str = None) -> Dict[str, Any]:
        """
        Get job execution statistics.

        Args:
            job_name: Specific job name, or None for all jobs

        Returns:
            Job statistics dictionary
        """
        if job_name:
            return self.job_stats.get(job_name, {})
        return self.job_stats


# Module-level function for APScheduler serialization
def execute_scheduled_command(
    command: str,
    job_name: str,
    max_retries: int = 3,
    retry_delay_minutes: int = 15,
    timeout: int = 3600
) -> Dict[str, Any]:
    """
    Execute a scheduled command. This is a module-level function so APScheduler
    can serialize it for persistent storage.

    Args:
        command: Shell command to execute
        job_name: Name of the job for logging
        max_retries: Maximum retry attempts
        retry_delay_minutes: Delay between retries
        timeout: Command timeout in seconds

    Returns:
        Execution statistics dictionary
    """
    executor = CommandExecutor()
    return executor.execute_with_retry(
        command=command,
        job_name=job_name,
        max_retries=max_retries,
        retry_delay_minutes=retry_delay_minutes,
        timeout=timeout
    )
