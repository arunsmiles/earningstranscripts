"""
Setup configuration for earnings-data-client package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

setup(
    name="earnings-data-client",
    version="0.1.0",
    description="Download and query earnings call transcripts and SEC filings (10-K, 10-Q)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Arunath",
    author_email="umber-stack.79@icloud.com",
    url="https://github.com/arunsmiles/earningstranscripts",

    # Package discovery
    py_modules=[
        "config",
        "models",
        "indexer",
        "client",
        "fool_transcript_downloader",
        "sec_edgar_downloader",
        "sec_bulk_downloader",
    ],

    # Dependencies
    install_requires=[
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "selenium>=4.15.0",
        "lxml>=4.9.0",
    ],

    # Optional dependencies
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
    },

    # Python version requirement
    python_requires=">=3.8",

    # CLI entry points
    entry_points={
        "console_scripts": [
            "earnings-config=config:main",
            "earnings-index=indexer:main",
            "earnings-query=client:main",
            "earnings-download-transcripts=fool_transcript_downloader:main",
            "earnings-download-sec=sec_edgar_downloader:main",
            "earnings-download-bulk=sec_bulk_downloader:main",
        ],
    },

    # Classification
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],

    # Keywords
    keywords="earnings sec filings 10-K 10-Q transcripts financial data",

    # Project URLs
    project_urls={
        "Bug Reports": "https://github.com/arunsmiles/earningstranscripts/issues",
        "Source": "https://github.com/arunsmiles/earningstranscripts",
    },

    # Include package data
    include_package_data=True,
)
