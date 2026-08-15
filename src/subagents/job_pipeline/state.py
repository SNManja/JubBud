"""
In-memory cache and user selection resolver for JobBud's job pipeline.
Stores candidate jobs and acquisition statistics between tool calls.
"""

import re
from typing import List, Dict, Any, Optional

# In-memory cache for candidate jobs returned by board fetchers
LAST_FETCHED_JOBS_CACHE: List[Dict[str, Any]] = []
LAST_FETCHED_STATS_CACHE: Dict[str, Any] = {
    "total_raw": 0,
    "pre_discarded": 0,
    "pre_discarded_summary": [],
}


def set_last_fetched_jobs_cache(
    jobs: List[Dict[str, Any]],
    total_raw: int = 0,
    pre_discarded_summary: Optional[List[str]] = None,
) -> None:
    """Caches candidate jobs and Stage 1/2 fetch stats in memory."""
    global LAST_FETCHED_JOBS_CACHE, LAST_FETCHED_STATS_CACHE
    LAST_FETCHED_JOBS_CACHE = list(jobs)
    summary = list(pre_discarded_summary) if pre_discarded_summary else []
    LAST_FETCHED_STATS_CACHE = {
        "total_raw": total_raw if total_raw > 0 else (len(jobs) + len(summary)),
        "pre_discarded": len(summary),
        "pre_discarded_summary": summary,
    }


def get_last_fetched_stats_cache() -> Dict[str, Any]:
    """Returns stored Stage 1/2 acquisition & pre-filter stats."""
    return dict(LAST_FETCHED_STATS_CACHE)


def resolve_jobs_from_selection(selection_str: str) -> List[Dict[str, Any]]:
    """
    Parses user selection string (e.g. "1, 3", "1, 2, 5", "del 1 al 4", "todas")
    and returns selected jobs from LAST_FETCHED_JOBS_CACHE.
    """
    if not LAST_FETCHED_JOBS_CACHE:
        return []

    sel = selection_str.strip().lower()
    if sel in ("todas", "all", "todos", "*"):
        return list(LAST_FETCHED_JOBS_CACHE)

    # Check for range patterns like "del 1 al 4", "1-4", "1 a 4"
    range_match = re.search(r'(?:del\s*)?(\d+)\s*(?:a|al|-)\s*(\d+)', sel)
    if range_match:
        start_idx = max(1, int(range_match.group(1)))
        end_idx = min(len(LAST_FETCHED_JOBS_CACHE), int(range_match.group(2)))
        return LAST_FETCHED_JOBS_CACHE[start_idx - 1 : end_idx]

    # Check for individual digit patterns like "1, 2, 5"
    digits = [int(d) for d in re.findall(r'\b\d+\b', sel)]
    selected = []
    for d in digits:
        if 1 <= d <= len(LAST_FETCHED_JOBS_CACHE):
            selected.append(LAST_FETCHED_JOBS_CACHE[d - 1])

    return selected if selected else list(LAST_FETCHED_JOBS_CACHE)
