"""
Multi-board sequential pipeline orchestrator for JobBud.
Coordinates automated, deterministic analysis across registered job boards.
"""

import time
from typing import List, Dict, Any

from src.tools.boards import (
    _load_board_urls,
    _sort_boards_deterministically,
    get_board_to_analyze,
)
from src.subagents.job_pipeline.config import load_pipeline_config
from src.subagents.job_pipeline.scope_parser import filter_boards_by_scope
from src.subagents.job_pipeline.single_pipeline import run_job_processing_pipeline
from src.subagents.job_pipeline.reporter import format_multi_board_report


def run_multi_board_pipeline(scope_str: str = "unanalyzed") -> Dict[str, Any]:
    """
    Executes the automated multi-board sequential pipeline over registered job boards.

    Args:
        scope_str: Scope filter ('unanalyzed', 'all', '1, 2, 5', '1d', 'before:YYYY-MM-DD', etc.)

    Returns:
        Dict containing aggregated telemetry metrics, top recommendations, and consolidated report.
    """
    cfg = load_pipeline_config()
    delay_between_boards = cfg.get("delay_between_boards_seconds", 10.0)

    all_boards = _load_board_urls()
    if not all_boards:
        return {
            "boards_analyzed": 0,
            "total_raw": 0,
            "pre_discarded_count": 0,
            "pre_passed_count": 0,
            "post_discarded_count": 0,
            "deduped_count": 0,
            "capped_count": 0,
            "sent_to_ranker_count": 0,
            "successfully_ranked_count": 0,
            "ranking_errors_count": 0,
            "passed_count": 0,
            "top_recommendations": [],
            "report_markdown": "No hay tableros registrados en profile/board_urls.json para analizar.",
        }

    sorted_boards = _sort_boards_deterministically(all_boards)
    target_boards = filter_boards_by_scope(sorted_boards, scope_str)

    if not target_boards:
        return {
            "boards_analyzed": 0,
            "total_raw": 0,
            "pre_discarded_count": 0,
            "pre_passed_count": 0,
            "post_discarded_count": 0,
            "deduped_count": 0,
            "capped_count": 0,
            "sent_to_ranker_count": 0,
            "successfully_ranked_count": 0,
            "ranking_errors_count": 0,
            "passed_count": 0,
            "top_recommendations": [],
            "report_markdown": f"No hay tableros que coincidan con el criterio de selección '{scope_str}' (ej. sin analizar o vencidos).",
        }

    total_raw_sum = 0
    total_pre_discarded_sum = 0
    total_pre_passed_sum = 0
    total_post_discarded_sum = 0
    total_deduped_sum = 0
    total_capped_sum = 0
    total_sent_to_ranker_sum = 0
    total_successfully_ranked_sum = 0
    total_ranking_errors_sum = 0
    total_passed_sum = 0

    analyzed_board_names: List[str] = []
    all_newly_ranked_jobs: List[Dict[str, Any]] = []

    for idx, board in enumerate(target_boards, start=1):
        if idx > 1 and delay_between_boards > 0:
            time.sleep(delay_between_boards)

        b_name = board.get("name", "Board")
        b_id = board.get("id") or b_name
        analyzed_board_names.append(b_name)

        # Triggers fetchers and stores raw jobs in cache
        get_board_to_analyze(b_id)

        # Executes single board pipeline for all candidates
        pipe_res = run_job_processing_pipeline("todas")

        total_raw_sum += pipe_res.get("total_raw", 0)
        total_pre_discarded_sum += pipe_res.get("pre_discarded_count", 0)
        total_pre_passed_sum += pipe_res.get("pre_passed_count", 0)
        total_post_discarded_sum += pipe_res.get("post_discarded_count", 0)
        total_deduped_sum += pipe_res.get("deduped_count", 0)
        total_capped_sum += pipe_res.get("capped_count", 0)
        total_sent_to_ranker_sum += pipe_res.get("sent_to_ranker_count", 0)
        total_successfully_ranked_sum += pipe_res.get("successfully_ranked_count", 0)
        total_ranking_errors_sum += pipe_res.get("ranking_errors_count", 0)
        total_passed_sum += pipe_res.get("passed_count", 0)

        for rj in pipe_res.get("ranked_jobs", []):
            all_newly_ranked_jobs.append(rj)

    all_newly_ranked_jobs.sort(key=lambda j: j.get("score") or 0, reverse=True)
    top_5_jobs = all_newly_ranked_jobs[:5]

    report_markdown = format_multi_board_report(
        scope_str=scope_str,
        analyzed_board_names=analyzed_board_names,
        delay_between_boards=delay_between_boards,
        total_raw_sum=total_raw_sum,
        total_pre_discarded_sum=total_pre_discarded_sum,
        total_pre_passed_sum=total_pre_passed_sum,
        total_post_discarded_sum=total_post_discarded_sum,
        total_deduped_sum=total_deduped_sum,
        total_capped_sum=total_capped_sum,
        total_sent_to_ranker_sum=total_sent_to_ranker_sum,
        total_passed_sum=total_passed_sum,
        top_5_jobs=top_5_jobs,
    )

    return {
        "boards_analyzed": len(analyzed_board_names),
        "total_raw": total_raw_sum,
        "pre_discarded_count": total_pre_discarded_sum,
        "pre_passed_count": total_pre_passed_sum,
        "post_discarded_count": total_post_discarded_sum,
        "deduped_count": total_deduped_sum,
        "capped_count": total_capped_sum,
        "sent_to_ranker_count": total_sent_to_ranker_sum,
        "successfully_ranked_count": total_successfully_ranked_sum,
        "ranking_errors_count": total_ranking_errors_sum,
        "passed_count": total_passed_sum,
        "top_recommendations": top_5_jobs,
        "report_markdown": report_markdown,
    }
