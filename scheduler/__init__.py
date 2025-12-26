"""
Earnings Transcript Scheduler

A production-ready scheduling system for automating earnings transcript
and SEC filing downloads using APScheduler with persistent job queues.

Features:
- Dynamic job management (add/remove/modify jobs at runtime)
- Persistent job storage (survives restarts)
- Cron-style scheduling
- Concurrent job execution
- One-time and recurring jobs
- Job event logging
"""

from scheduler.service import SchedulerService
from scheduler.jobs import JobManager
from scheduler.config import SchedulerConfig

__version__ = "0.1.0"
__all__ = ["SchedulerService", "JobManager", "SchedulerConfig"]
