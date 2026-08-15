"""
Deterministic 6-stage sequential job processing pipeline for JobBud.
Processes a batch or single board selection from raw fetch to ranked persistence.
"""

import json
import math
import time
from typing import List, Dict, Any, Tuple, Optional

from src.tools.queries import evaluate_post_parse_filters
from src.subagents.job_parser.tools import _generate_stable_job_id
from src.subagents.job_ranker.tools import (
    JOBS_FILE_PATH,
    set_ranking_batch_cache,
    clear_ranking_batch_cache,
)
from src.subagents.job_pipeline.config import load_pipeline_config
from src.subagents.job_pipeline.state import (
    LAST_FETCHED_JOBS_CACHE,
    get_last_fetched_stats_cache,
    resolve_jobs_from_selection,
)
from src.subagents.job_pipeline.adk_clients import evaluate_ranking_chunk_with_adk
from src.subagents.job_pipeline.reporter import format_single_pipeline_report
from src.fetchers.manual import ingest_manual_job


def _ensure_stable_job_id(pdict: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures a job dictionary has a valid, deterministic ID."""
    if not pdict.get("id") or str(pdict.get("id")).strip().lower() in (
        "none",
        "null",
        "undefined",
        "",
    ):
        pdict["id"] = _generate_stable_job_id(
            title=pdict.get("title", ""),
            company=pdict.get("company", ""),
            summary=pdict.get("summary", ""),
            source_page=pdict.get("source_page", ""),
            source_url=pdict.get("source_url", ""),
        )
    return pdict


def _structure_selected_jobs(selected_jobs: List[Any]) -> List[Dict[str, Any]]:
    """Stage 3: Normalizes any raw text inputs or confirms JobDict representation."""
    parsed_jobs = []
    for job in selected_jobs:
        if isinstance(job, dict):
            if job.get("title") == "Posición de Texto Crudo" and job.get("raw_text"):
                manual_list = ingest_manual_job(job["raw_text"])
                pdict = manual_list[0] if manual_list else job
            else:
                pdict = job
        elif isinstance(job, str):
            manual_list = ingest_manual_job(job)
            if manual_list:
                pdict = manual_list[0]
            else:
                continue
        else:
            continue

        pdict = _ensure_stable_job_id(pdict)
        parsed_jobs.append(pdict)
    return parsed_jobs


def _load_existing_job_ids() -> Tuple[set, Optional[str]]:
    """Loads existing lowercase job IDs from jobs.json or returns error string if corrupted."""
    if not JOBS_FILE_PATH.exists():
        return set(), None

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            all_stored = json.load(f)
            if not isinstance(all_stored, list):
                return set(), f"{JOBS_FILE_PATH} no contiene una lista JSON válida de vacantes."
            return {
                str(j.get("id")).strip().lower()
                for j in all_stored
                if isinstance(j, dict) and j.get("id")
            }, None
    except Exception as e:
        return set(), f"Error al leer/validar {JOBS_FILE_PATH}: {str(e)}"


def _hydrate_ranked_jobs(jobs_to_rank: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-hydrates job dictionaries from jobs.json post-ranking to include score and rationale."""
    if not JOBS_FILE_PATH.exists():
        return jobs_to_rank

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            all_stored = json.load(f)
        stored_by_id = {
            str(j.get("id")).strip().lower(): j
            for j in all_stored
            if isinstance(j, dict) and j.get("id")
        }

        hydrated = []
        for vj in jobs_to_rank:
            v_id = str(vj.get("id", "")).strip().lower()
            if v_id in stored_by_id and stored_by_id[v_id].get("status") == "ranked":
                hydrated.append(stored_by_id[v_id])
            else:
                hydrated.append(vj)
        return hydrated
    except Exception:
        return jobs_to_rank


def run_job_processing_pipeline(selected_jobs: Any) -> Dict[str, Any]:
    """
    Executes the deterministic sequential job processing pipeline over selected jobs.

    Args:
        selected_jobs: Selection string (e.g. "1, 3", "todas") or List of job dicts.

    Returns:
        Dict containing exact 8-field telemetry counts, ranked_jobs, and report_markdown.
    """
    cfg = load_pipeline_config()
    max_jobs_per_board = cfg.get("max_jobs_per_board")
    delay_between_batches = cfg.get("delay_between_batches_seconds", 3.0)

    stats = get_last_fetched_stats_cache()
    is_full_selection = False

    if isinstance(selected_jobs, str):
        sel_lower = selected_jobs.strip().lower()
        if sel_lower in ("todas", "all", "todos", "*"):
            is_full_selection = True
        selected_jobs = resolve_jobs_from_selection(selected_jobs)

    if not selected_jobs:
        return {
            "total_raw": stats.get("total_raw", 0),
            "pre_discarded_count": stats.get("pre_discarded", 0),
            "pre_passed_count": 0,
            "post_discarded_count": 0,
            "deduped_count": 0,
            "capped_count": 0,
            "sent_to_ranker_count": 0,
            "successfully_ranked_count": 0,
            "ranking_errors_count": 0,
            "passed_count": 0,
            "ranked_jobs": [],
            "report_markdown": "No valid positions were selected for processing.",
        }

    pre_discarded_count = stats.get("pre_discarded", 0)
    pre_discarded_summary = stats.get("pre_discarded_summary", [])
    if is_full_selection or len(selected_jobs) == len(LAST_FETCHED_JOBS_CACHE):
        total_raw = stats.get("total_raw") or len(selected_jobs)
    else:
        total_raw = len(selected_jobs) + pre_discarded_count

    pre_passed_count = len(selected_jobs)

    # Stage 3: Structuring / Parsing in memory
    parsed_jobs = _structure_selected_jobs(selected_jobs)

    # Stage 4: Deterministic Post-Parse Filtering (Python / 0 Tokens)
    valid_jobs = []
    discarded_jobs = []
    for pjob in parsed_jobs:
        passed, reason = evaluate_post_parse_filters(pjob)
        if passed:
            valid_jobs.append(pjob)
        else:
            discarded_jobs.append((pjob, reason))

    post_discarded_count = len(discarded_jobs)

    # Stage 4: Deduplication against jobs.json (Dedupe BEFORE Cap)
    existing_ids, err_msg = _load_existing_job_ids()
    if err_msg:
        report_markdown = f"❌ **Error Crítico en Pipeline:**\n- {err_msg}\n- El pipeline fue abortado por seguridad."
        return {
            "total_raw": total_raw,
            "pre_discarded_count": pre_discarded_count,
            "pre_passed_count": pre_passed_count,
            "post_discarded_count": post_discarded_count,
            "deduped_count": 0,
            "capped_count": 0,
            "sent_to_ranker_count": 0,
            "successfully_ranked_count": 0,
            "ranking_errors_count": 0,
            "passed_count": 0,
            "ranked_jobs": [],
            "report_markdown": report_markdown,
        }

    new_jobs = [j for j in valid_jobs if str(j.get("id", "")).strip().lower() not in existing_ids]
    deduped_count = len(valid_jobs) - len(new_jobs)

    # Stage 4: Optional Capping (applied ONLY to new_jobs)
    capped_jobs = []
    if max_jobs_per_board is not None and max_jobs_per_board > 0 and len(new_jobs) > max_jobs_per_board:
        capped_jobs = new_jobs[max_jobs_per_board:]
        jobs_to_rank = new_jobs[:max_jobs_per_board]
    else:
        jobs_to_rank = new_jobs

    capped_count = len(capped_jobs)

    if not jobs_to_rank:
        report = format_single_pipeline_report(
            total_raw=total_raw,
            pre_discarded_count=pre_discarded_count,
            pre_passed_count=pre_passed_count,
            post_discarded_count=post_discarded_count,
            deduped_count=deduped_count,
            capped_count=capped_count,
            successfully_ranked_count=0,
            pre_discarded_summary=pre_discarded_summary,
            discarded_jobs=discarded_jobs,
            capped_jobs=capped_jobs,
            max_jobs_per_board=max_jobs_per_board,
        )
        return {
            "total_raw": total_raw,
            "pre_discarded_count": pre_discarded_count,
            "pre_passed_count": pre_passed_count,
            "post_discarded_count": post_discarded_count,
            "deduped_count": deduped_count,
            "capped_count": capped_count,
            "sent_to_ranker_count": 0,
            "successfully_ranked_count": 0,
            "ranking_errors_count": 0,
            "passed_count": 0,
            "ranked_jobs": [],
            "report_markdown": report,
        }

    # Stage 5: Chunking with k = min(5, ceil(R / 4))
    R = len(jobs_to_rank)
    k = max(1, min(5, math.ceil(R / 4)))
    chunks = [jobs_to_rank[i : i + k] for i in range(0, R, k)]

    ranked_results: List[Tuple[List[Dict[str, Any]], str]] = []
    for chunk_idx, chunk in enumerate(chunks, start=1):
        if chunk_idx > 1 and delay_between_batches > 0:
            time.sleep(delay_between_batches)
        try:
            set_ranking_batch_cache(chunk)
            ranker_output = evaluate_ranking_chunk_with_adk(chunk)
            ranked_results.append((chunk, ranker_output))
        finally:
            clear_ranking_batch_cache()

    # Stage 6: Hydrate and Consolidate
    ranked_hydrated_jobs = _hydrate_ranked_jobs(jobs_to_rank)
    successfully_ranked_count = len(ranked_hydrated_jobs)
    ranking_errors_count = max(0, len(jobs_to_rank) - successfully_ranked_count)

    report_markdown = format_single_pipeline_report(
        total_raw=total_raw,
        pre_discarded_count=pre_discarded_count,
        pre_passed_count=pre_passed_count,
        post_discarded_count=post_discarded_count,
        deduped_count=deduped_count,
        capped_count=capped_count,
        successfully_ranked_count=successfully_ranked_count,
        k=k,
        pre_discarded_summary=pre_discarded_summary,
        discarded_jobs=discarded_jobs,
        capped_jobs=capped_jobs,
        max_jobs_per_board=max_jobs_per_board,
        ranked_results=ranked_results,
    )

    return {
        "total_raw": total_raw,
        "pre_discarded_count": pre_discarded_count,
        "pre_passed_count": pre_passed_count,
        "post_discarded_count": post_discarded_count,
        "deduped_count": deduped_count,
        "capped_count": capped_count,
        "sent_to_ranker_count": len(jobs_to_rank),
        "successfully_ranked_count": successfully_ranked_count,
        "ranking_errors_count": ranking_errors_count,
        "passed_count": successfully_ranked_count,
        "ranked_jobs": ranked_hydrated_jobs,
        "report_markdown": report_markdown,
    }
