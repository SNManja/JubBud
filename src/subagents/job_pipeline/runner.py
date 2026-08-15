"""
JobBud Sequential Pipeline Runner (Backward Compatibility Facade).

This module re-exports components from the modular job_pipeline submodules:
- config: load_pipeline_config, PIPELINE_CONFIG_PATH
- state: LAST_FETCHED_JOBS_CACHE, set_last_fetched_jobs_cache, get_last_fetched_stats_cache, resolve_jobs_from_selection
- single_pipeline: run_job_processing_pipeline
- scope_parser: filter_boards_by_scope
- multi_pipeline: run_multi_board_pipeline
"""

from src.subagents.job_pipeline.config import load_pipeline_config, PIPELINE_CONFIG_PATH
from src.subagents.job_pipeline.state import (
    LAST_FETCHED_JOBS_CACHE,
    LAST_FETCHED_STATS_CACHE,
    set_last_fetched_jobs_cache,
    get_last_fetched_stats_cache,
    resolve_jobs_from_selection,
)
from src.subagents.job_pipeline.scope_parser import filter_boards_by_scope
from src.subagents.job_pipeline.single_pipeline import run_job_processing_pipeline
from src.subagents.job_pipeline.multi_pipeline import run_multi_board_pipeline

__all__ = [
    "PIPELINE_CONFIG_PATH",
    "load_pipeline_config",
    "LAST_FETCHED_JOBS_CACHE",
    "LAST_FETCHED_STATS_CACHE",
    "set_last_fetched_jobs_cache",
    "get_last_fetched_stats_cache",
    "resolve_jobs_from_selection",
    "filter_boards_by_scope",
    "run_job_processing_pipeline",
    "run_multi_board_pipeline",
]
