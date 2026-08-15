"""
Fetchers Package for JobBud.

Provides unified acquisition, normalization adapters, and agent tools:
- greenhouse: fetch_greenhouse_jobs, fetch_greenhouse_job_content, parse_greenhouse_url
- exactas: fetch_exactas_jobs, fetch_exactas_job_board
- linkedin: fetch_linkedin_job, fetch_linkedin_job_content
- manual: ingest_manual_job
- base: compress_job_text, extract_technologies_from_text
"""

from src.fetchers.base import compress_job_text, extract_technologies_from_text
from src.fetchers.greenhouse import (
    fetch_greenhouse_jobs,
    fetch_greenhouse_job_content,
    parse_greenhouse_url,
)
from src.fetchers.exactas import fetch_exactas_jobs, fetch_exactas_job_board
from src.fetchers.linkedin import fetch_linkedin_job, fetch_linkedin_job_content
from src.fetchers.manual import ingest_manual_job

__all__ = [
    "compress_job_text",
    "extract_technologies_from_text",
    "fetch_greenhouse_jobs",
    "fetch_greenhouse_job_content",
    "parse_greenhouse_url",
    "fetch_exactas_jobs",
    "fetch_exactas_job_board",
    "fetch_linkedin_job",
    "fetch_linkedin_job_content",
    "ingest_manual_job",
]
