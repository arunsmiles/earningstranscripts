"""
Job definitions and execution management.

Defines different job types (transcripts, SEC filings, indexing) and
handles their execution with error handling and logging.
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class JobExecutionError(Exception):
    """Raised when job execution fails."""
    pass


class JobManager:
    """
    Manages job execution for different job types.

    Supports:
    - Transcript downloads
    - SEC filing downloads
    - Indexing operations
    - Custom scripts
    """

    def __init__(self, config=None):
        """
        Initialize job manager.

        Args:
            config: Optional Config instance for data directory
        """
        self.config = config
        self.job_stats = {}  # Track job execution statistics

    def create_job_function(self, job_type: str, options: Dict[str, Any]) -> Callable:
        """
        Create executable job function based on job type.

        Args:
            job_type: Type of job ('transcripts', 'sec', 'index', 'custom')
            options: Job-specific options

        Returns:
            Callable job function

        Raises:
            ValueError: If job_type is unknown
        """
        job_functions = {
            'transcripts': self._create_transcript_job,
            'sec': self._create_sec_job,
            'index': self._create_index_job,
            'custom': self._create_custom_job
        }

        if job_type not in job_functions:
            raise ValueError(f"Unknown job type: {job_type}")

        return job_functions[job_type](options)

    def _create_transcript_job(self, options: Dict[str, Any]) -> Callable:
        """Create transcript download job."""
        def job():
            logger.info("Starting transcript download job")
            logger.debug(f"Options: {options}")

            try:
                # Import here to avoid circular dependencies
                from fool_transcript_downloader import FoolTranscriptDownloader
                from config import get_config

                # Get config
                config = self.config or get_config()

                # Create downloader instance
                downloader = FoolTranscriptDownloader(
                    data_dir=str(config.data_dir),
                    verbose=options.get('verbose', False)
                )

                # Extract options
                ticker = options.get('ticker')
                all_transcripts = options.get('all', False)
                from_date = options.get('from')
                to_date = options.get('to')
                delay = options.get('delay', 1.0)

                # Execute download
                if all_transcripts:
                    logger.info("Downloading all historical transcripts")
                    downloader.download_all_transcripts(delay=delay)
                elif ticker:
                    logger.info(f"Downloading transcripts for ticker: {ticker}")
                    downloader.download_ticker(ticker, delay=delay)
                elif from_date or to_date:
                    logger.info(f"Downloading transcripts from {from_date} to {to_date}")
                    downloader.download_date_range(
                        from_date=from_date,
                        to_date=to_date,
                        delay=delay
                    )
                else:
                    # Default: download current month
                    logger.info("Downloading current month transcripts")
                    downloader.download_current_month(delay=delay)

                logger.info("Transcript download job completed successfully")

            except Exception as e:
                logger.error(f"Transcript download job failed: {e}", exc_info=True)
                raise JobExecutionError(f"Transcript download failed: {e}") from e

        return job

    def _create_sec_job(self, options: Dict[str, Any]) -> Callable:
        """Create SEC filing download job."""
        def job():
            logger.info("Starting SEC filing download job")
            logger.debug(f"Options: {options}")

            try:
                from sec_edgar_downloader import SECEdgarDownloader
                from config import get_config

                config = self.config or get_config()

                downloader = SECEdgarDownloader(
                    data_dir=str(config.data_dir)
                )

                tickers = options.get('tickers', [])
                forms = options.get('forms', ['10-K', '10-Q'])
                from_date = options.get('from')
                to_date = options.get('to')
                all_filings = options.get('all', False)

                if not tickers:
                    logger.warning("No tickers specified for SEC download")
                    return

                for ticker in tickers:
                    logger.info(f"Downloading SEC filings for {ticker}: {forms}")
                    downloader.download(
                        ticker=ticker,
                        forms=forms,
                        from_date=from_date,
                        to_date=to_date,
                        download_all=all_filings
                    )

                logger.info("SEC filing download job completed successfully")

            except Exception as e:
                logger.error(f"SEC filing download job failed: {e}", exc_info=True)
                raise JobExecutionError(f"SEC download failed: {e}") from e

        return job

    def _create_index_job(self, options: Dict[str, Any]) -> Callable:
        """Create indexing job."""
        def job():
            logger.info("Starting indexing job")
            logger.debug(f"Options: {options}")

            try:
                from indexer import TranscriptIndexer
                from config import get_config

                config = self.config or get_config()

                indexer = TranscriptIndexer(data_dir=str(config.data_dir))

                # Run indexing
                rebuild = options.get('rebuild', False)
                if rebuild:
                    logger.info("Rebuilding index from scratch")
                    indexer.rebuild_index()
                else:
                    logger.info("Updating index")
                    indexer.update_index()

                logger.info("Indexing job completed successfully")

            except Exception as e:
                logger.error(f"Indexing job failed: {e}", exc_info=True)
                raise JobExecutionError(f"Indexing failed: {e}") from e

        return job

    def _create_custom_job(self, options: Dict[str, Any]) -> Callable:
        """Create custom script job."""
        def job():
            logger.info("Starting custom job")
            logger.debug(f"Options: {options}")

            try:
                script_path = options.get('script')
                if not script_path:
                    raise ValueError("Custom job requires 'script' option")

                script_path = Path(script_path).expanduser()
                if not script_path.exists():
                    raise FileNotFoundError(f"Script not found: {script_path}")

                # Execute script
                import subprocess
                result = subprocess.run(
                    [str(script_path)],
                    capture_output=True,
                    text=True,
                    check=True
                )

                logger.info(f"Custom job output: {result.stdout}")
                logger.info("Custom job completed successfully")

            except Exception as e:
                logger.error(f"Custom job failed: {e}", exc_info=True)
                raise JobExecutionError(f"Custom job failed: {e}") from e

        return job

    def execute_with_retry(
        self,
        job_func: Callable,
        job_name: str,
        max_retries: int = 3,
        retry_delay_minutes: int = 15
    ) -> Dict[str, Any]:
        """
        Execute job with retry logic and statistics tracking.

        Args:
            job_func: Job function to execute
            job_name: Name of the job for logging
            max_retries: Maximum number of retry attempts
            retry_delay_minutes: Delay between retries in minutes

        Returns:
            Dict with execution statistics

        Raises:
            JobExecutionError: If job fails after all retries
        """
        start_time = datetime.now()
        attempt = 0
        last_error = None

        while attempt < max_retries:
            try:
                logger.info(f"Executing job '{job_name}' (attempt {attempt + 1}/{max_retries})")

                # Execute job
                job_func()

                # Success
                duration = (datetime.now() - start_time).total_seconds()
                stats = {
                    'job_name': job_name,
                    'status': 'success',
                    'duration_seconds': duration,
                    'attempts': attempt + 1,
                    'timestamp': datetime.now().isoformat()
                }

                self.job_stats[job_name] = stats
                logger.info(f"Job '{job_name}' completed in {duration:.2f}s")
                return stats

            except Exception as e:
                last_error = e
                attempt += 1

                if attempt < max_retries:
                    delay_seconds = retry_delay_minutes * 60
                    logger.warning(
                        f"Job '{job_name}' failed (attempt {attempt}/{max_retries}): {e}"
                    )
                    logger.info(f"Retrying in {retry_delay_minutes} minutes...")
                    time.sleep(delay_seconds)
                else:
                    logger.error(f"Job '{job_name}' failed after {max_retries} attempts")

        # All retries exhausted
        duration = (datetime.now() - start_time).total_seconds()
        stats = {
            'job_name': job_name,
            'status': 'failed',
            'duration_seconds': duration,
            'attempts': max_retries,
            'error': str(last_error),
            'timestamp': datetime.now().isoformat()
        }

        self.job_stats[job_name] = stats
        raise JobExecutionError(
            f"Job '{job_name}' failed after {max_retries} attempts: {last_error}"
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
