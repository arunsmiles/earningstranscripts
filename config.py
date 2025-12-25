"""
Configuration management for earnings data storage.

This module provides a centralized configuration system for managing
data directory locations. All data writes (transcripts, SEC filings, cache)
will go to subdirectories under the configured base data directory.
"""

import os
import json
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default data directory locations
DEFAULT_DATA_DIR = os.path.expanduser("~/.earnings_data")
CONFIG_FILE = os.path.expanduser("~/.earnings_data/config.json")

# Environment variable to override data directory
ENV_DATA_DIR = "EARNINGS_DATA_DIR"


class Config:
    """
    Configuration manager for earnings data storage.

    Data directory resolution order (highest to lowest priority):
    1. Explicitly passed data_dir parameter
    2. EARNINGS_DATA_DIR environment variable
    3. Config file (~/.earnings_data/config.json)
    4. Default (~/.earnings_data)

    Directory structure:
        {data_dir}/
        ├── transcripts/       # Earnings call transcripts
        ├── secfilings/        # SEC filings (10-K, 10-Q, etc.)
        ├── cache/             # SEC bulk data cache
        └── metadata.db        # Metadata index database
    """

    _instance: Optional['Config'] = None

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            data_dir: Base directory for all data storage. If None, will be
                     resolved from environment variable, config file, or default.
        """
        self.data_dir = self._resolve_data_dir(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.transcripts_dir = self.data_dir / "transcripts"
        self.secfilings_dir = self.data_dir / "secfilings"
        self.cache_dir = self.data_dir / "cache"
        self.metadata_db = self.data_dir / "metadata.db"

        # Create subdirectories
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.secfilings_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Earnings data directory: {self.data_dir}")
        logger.debug(f"  Transcripts: {self.transcripts_dir}")
        logger.debug(f"  SEC filings: {self.secfilings_dir}")
        logger.debug(f"  Cache: {self.cache_dir}")
        logger.debug(f"  Metadata DB: {self.metadata_db}")

    def _resolve_data_dir(self, data_dir: Optional[str]) -> Path:
        """
        Resolve data directory from multiple sources.

        Priority:
        1. Explicitly passed data_dir
        2. EARNINGS_DATA_DIR environment variable
        3. Config file
        4. Default
        """
        # 1. Explicit parameter (highest priority)
        if data_dir:
            logger.debug(f"Using explicitly provided data_dir: {data_dir}")
            return Path(data_dir).expanduser().resolve()

        # 2. Environment variable
        env_dir = os.getenv(ENV_DATA_DIR)
        if env_dir:
            logger.debug(f"Using data_dir from {ENV_DATA_DIR}: {env_dir}")
            return Path(env_dir).expanduser().resolve()

        # 3. Config file
        config_dir = self._load_from_config_file()
        if config_dir:
            logger.debug(f"Using data_dir from config file: {config_dir}")
            return Path(config_dir).expanduser().resolve()

        # 4. Default
        logger.debug(f"Using default data_dir: {DEFAULT_DATA_DIR}")
        return Path(DEFAULT_DATA_DIR).expanduser().resolve()

    def _load_from_config_file(self) -> Optional[str]:
        """Load data directory from config file if it exists."""
        try:
            config_path = Path(CONFIG_FILE).expanduser()
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    return config_data.get('data_dir')
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")
        return None

    def save_config(self):
        """Save current configuration to config file."""
        config_path = Path(CONFIG_FILE).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config_data = {
            'data_dir': str(self.data_dir)
        }

        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Saved configuration to {config_path}")

    @classmethod
    def get_instance(cls, data_dir: Optional[str] = None) -> 'Config':
        """
        Get or create singleton Config instance.

        Args:
            data_dir: Base directory for data storage

        Returns:
            Config instance
        """
        if cls._instance is None or data_dir is not None:
            cls._instance = Config(data_dir)
        return cls._instance

    def __repr__(self):
        return f"Config(data_dir={self.data_dir})"


def get_config(data_dir: Optional[str] = None) -> Config:
    """
    Get the global configuration instance.

    Args:
        data_dir: Optional data directory to use. If provided, will create
                 a new Config instance with this directory.

    Returns:
        Config instance
    """
    return Config.get_instance(data_dir)


def set_data_directory(data_dir: str, save: bool = True):
    """
    Set the data directory and optionally save to config file.

    Args:
        data_dir: Path to base data directory
        save: If True, save configuration to config file

    Returns:
        Config instance
    """
    config = Config(data_dir)
    Config._instance = config

    if save:
        config.save_config()

    return config


def get_data_directory() -> Path:
    """Get the current data directory path."""
    return get_config().data_dir


if __name__ == "__main__":
    # CLI for managing configuration
    import argparse

    parser = argparse.ArgumentParser(description="Manage earnings data configuration")
    parser.add_argument(
        '--set-dir',
        type=str,
        help='Set data directory and save to config'
    )
    parser.add_argument(
        '--show',
        action='store_true',
        help='Show current configuration'
    )
    parser.add_argument(
        '--init',
        action='store_true',
        help='Initialize data directory structure'
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.set_dir:
        config = set_data_directory(args.set_dir, save=True)
        print(f"✓ Data directory set to: {config.data_dir}")
        print(f"✓ Configuration saved to: {CONFIG_FILE}")
    elif args.show:
        config = get_config()
        print("Current configuration:")
        print(f"  Data directory: {config.data_dir}")
        print(f"  Transcripts:    {config.transcripts_dir}")
        print(f"  SEC filings:    {config.secfilings_dir}")
        print(f"  Cache:          {config.cache_dir}")
        print(f"  Metadata DB:    {config.metadata_db}")
    elif args.init:
        config = get_config()
        print(f"✓ Initialized data directory at: {config.data_dir}")
        print(f"  Created subdirectories:")
        print(f"    - {config.transcripts_dir}")
        print(f"    - {config.secfilings_dir}")
        print(f"    - {config.cache_dir}")
    else:
        parser.print_help()
