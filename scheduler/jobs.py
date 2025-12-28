"""
Generic command execution for scheduled jobs.

Executes shell commands with error handling, timeout, and logging.
The scheduler is completely decoupled from specific tools - it simply
runs whatever command you specify.
"""

import logging
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


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
        timeout: Optional[int] = 3600
    ) -> Dict[str, Any]:
        """
        Execute command with retry logic and statistics tracking.

        Args:
            command: Shell command to execute
            job_name: Name of the job for logging
            max_retries: Maximum number of retry attempts
            retry_delay_minutes: Delay between retries in minutes
            timeout: Command timeout in seconds

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
        
        logger.info(f"{log_prefix} Starting job run")

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
                duration = (datetime.now() - start_time).total_seconds()
                stats = {
                    'job_name': job_name,
                    'run_id': run_id,
                    'command': command,
                    'status': 'success',
                    'duration_seconds': duration,
                    'attempts': attempt + 1,
                    'returncode': result['returncode'],
                    'timestamp': datetime.now().isoformat()
                }

                self.job_stats[job_name] = stats
                logger.info(f"{log_prefix} Completed successfully in {duration:.2f}s")
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
        duration = (datetime.now() - start_time).total_seconds()
        stats = {
            'job_name': job_name,
            'run_id': run_id,
            'command': command,
            'status': 'failed',
            'duration_seconds': duration,
            'attempts': max_retries,
            'error': str(last_error),
            'timestamp': datetime.now().isoformat()
        }

        self.job_stats[job_name] = stats
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
