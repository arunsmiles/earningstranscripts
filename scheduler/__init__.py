"""
Generic Command Scheduler

A production-ready scheduling system for running any shell command
on a schedule using APScheduler with persistent job queues.

Features:
- Generic command execution (scheduler is decoupled from specific tools)
- Dynamic job management (add/remove/modify jobs at runtime)
- Persistent job storage (survives restarts)
- Cron-style scheduling
- Concurrent job execution
- One-time and recurring jobs
- Job event logging
"""

from scheduler.service import SchedulerService
from scheduler.jobs import CommandExecutor
from scheduler.config import SchedulerConfig

__version__ = "0.2.0"
__all__ = ["SchedulerService", "CommandExecutor", "SchedulerConfig"]
