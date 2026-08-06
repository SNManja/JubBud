"""
Sequential Job Processing Pipeline Runner for JobBud.

Enforces strict, 100% deterministic sequential execution:
1. Parsing (if unparsed text) / In-memory dictionary structuring.
2. Deterministic Post-Parse Filtering in Python (blacklist_roles.md, blacklist_seniority.md, location_filters.json).
3. Chunking with k = min(5, ceil(R / 4)).
4. Batch ranking via job_ranker_agent.
5. Atomic write of ranked jobs to jobs.json (status: 'ranked').
"""

import math
from typing import List, Dict, Any, Tuple
from src.tools.queries import evaluate_post_parse_filters
from src.subagents.job_ranker.tools import read_candidate_profile, save_ranked_jobs_batch


# In-memory cache for candidate jobs returned by board fetchers
LAST_FETCHED_JOBS_CACHE: List[Dict[str, Any]] = []

def set_last_fetched_jobs_cache(jobs: List[Dict[str, Any]]):
    """Caches candidate jobs in memory to avoid passing huge JSON strings in LLM prompts."""
    global LAST_FETCHED_JOBS_CACHE
    LAST_FETCHED_JOBS_CACHE = list(jobs)

def resolve_jobs_from_selection(selection_str: str) -> List[Dict[str, Any]]:
    """
    Parses user selection string (e.g. "1, 3", "1, 2, 5", "del 1 al 4", "todas")
    and returns selected jobs from LAST_FETCHED_JOBS_CACHE.
    """
    import re
    if not LAST_FETCHED_JOBS_CACHE:
        return []

    sel = selection_str.strip().lower()
    if sel in ("todas", "all", "todos", "*"):
        return list(LAST_FETCHED_JOBS_CACHE)

    range_match = re.search(r'(?:del\s*)?(\d+)\s*(?:a|al|-)\s*(\d+)', sel)
    if range_match:
        start_idx = max(1, int(range_match.group(1)))
        end_idx = min(len(LAST_FETCHED_JOBS_CACHE), int(range_match.group(2)))
        return LAST_FETCHED_JOBS_CACHE[start_idx - 1:end_idx]

    digits = [int(d) for d in re.findall(r'\b\d+\b', sel)]
    selected = []
    for d in digits:
        if 1 <= d <= len(LAST_FETCHED_JOBS_CACHE):
            selected.append(LAST_FETCHED_JOBS_CACHE[d - 1])

    return selected if selected else list(LAST_FETCHED_JOBS_CACHE)


def run_job_processing_pipeline(selected_jobs: Any) -> Dict[str, Any]:
    """
    Executes the deterministic sequential job processing pipeline over selected jobs.

    Args:
        selected_jobs: Selection string (e.g. "1, 3") or List of job dicts.

    Returns:
        Dict containing total_processed, passed_count, discarded_count, ranked_jobs, and report_markdown.
    """
    if isinstance(selected_jobs, str):
        selected_jobs = resolve_jobs_from_selection(selected_jobs)

    if not selected_jobs:
        return {
            "total_processed": 0,
            "passed_count": 0,
            "discarded_count": 0,
            "ranked_jobs": [],
            "report_markdown": "No valid positions were selected for processing."
        }


    # Step 1: Parsing / Structuring in memory
    parsed_jobs = []
    for job in selected_jobs:
        if isinstance(job, dict):
            parsed_jobs.append(job)
        elif isinstance(job, str):
            # For raw text, structure via helper or parser
            from src.subagents.job_parser.tools import build_unified_job_dict
            udict = build_unified_job_dict(
                title="Posición de Texto Crudo",
                company="Not specified",
                location="Not specified",
                work_mode="Not specified",
                commitment="Not specified",
                salary_range="Not specified",
                key_technologies=[],
                main_requirements=[],
                summary=job[:300],
                raw_text=job,
                language="es",
                source_page="Manual"
            )
            parsed_jobs.append(udict)

    # Step 2: Deterministic Post-Parse Filtering (Python / 0 Tokens)
    valid_jobs = []
    discarded_jobs = []

    for pjob in parsed_jobs:
        passed, reason = evaluate_post_parse_filters(pjob)
        if passed:
            valid_jobs.append(pjob)
        else:
            discarded_jobs.append((pjob, reason))

    if not valid_jobs:
        discard_lines = [f"- **{j.get('title', 'Puesto')}**: {r}" for j, r in discarded_jobs]
        report = (
            f"📋 **Resultados del Procesamiento ({len(parsed_jobs)} seleccionadas):**\n"
            f"- 🚫 **Posiciones descartadas por filtros post-parseo:** {len(discarded_jobs)}\n"
            f"- ✅ **Posiciones válidas para rankear:** 0\n\n"
            f"**Motivos de descarte:**\n" + "\n".join(discard_lines)
        )
        return {
            "total_processed": len(parsed_jobs),
            "passed_count": 0,
            "discarded_count": len(discarded_jobs),
            "ranked_jobs": [],
            "report_markdown": report
        }

    # Step 3: Calculate Chunk Size k
    R = len(valid_jobs)
    k = max(1, min(5, math.ceil(R / 4)))
    chunks = [valid_jobs[i:i + k] for i in range(0, R, k)]

    # Step 4: Batch Ranking via JobRanker
    candidate_profile = read_candidate_profile()
    ranked_results = []

    for chunk_idx, chunk in enumerate(chunks, start=1):
        ranker_output = _evaluate_batch_chunk_with_adk_ranker(chunk)
        ranked_results.append((chunk, ranker_output))

    # Step 6: Generate Consolidated Report
    report_lines = [
        f"📊 **Reporte de Procesamiento Final ({len(parsed_jobs)} vacantes procesadas):**",
        f"- 🚫 **Descartadas por filtros (roles/seniority/ubicación):** {len(discarded_jobs)}",
        f"- ⭐ **Posiciones evaluadas y rankeadas con job_ranker_agent:** {len(valid_jobs)} (Lotes de {k} vacantes)",
        ""
    ]

    if discarded_jobs:
        report_lines.append("**Vacantes descartadas post-parseo:**")
        for j, r in discarded_jobs:
            report_lines.append(f"- ❌ **{j.get('title')}** en *{j.get('company')}* — *{r}*")
        report_lines.append("")

    report_lines.append("**Evaluaciones de Fit (job_ranker_agent):**\n")
    for chunk, output_text in ranked_results:
        report_lines.append(output_text)
        report_lines.append("\n---\n")

    return {
        "total_processed": len(parsed_jobs),
        "passed_count": len(valid_jobs),
        "discarded_count": len(discarded_jobs),
        "ranked_jobs": valid_jobs,
        "report_markdown": "\n".join(report_lines)
    }


def _evaluate_batch_chunk_with_adk_ranker(chunk: List[dict]) -> str:
    """
    Invokes job_ranker_agent via Google ADK InMemoryRunner to evaluate a batch chunk of jobs against candidate_profile.md.
    """
    import asyncio
    import json
    import concurrent.futures
    from google.genai import types
    from google.adk.runners import InMemoryRunner
    from src.subagents.job_ranker.job_ranker import job_ranker_agent

    runner = InMemoryRunner(agent=job_ranker_agent)
    session = runner.session_service.create_session_sync(user_id="jobbud_user", app_name=runner.app_name)

    prompt = (
        f"Evalúa la compatibilidad (fit) de las siguientes vacantes (lote) contra candidate_profile.md (usa read_candidate_profile) "
        f"y guarda los resultados en jobs.json usando save_ranked_jobs_batch:\n\n"
        f"{json.dumps(chunk, ensure_ascii=False, indent=2)}"
    )

    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    async def _run():
        output = []
        async for event in runner.run_async(user_id="jobbud_user", session_id=session.id, new_message=message):
            if hasattr(event, "content") and event.content and event.content.parts:
                for p in event.content.parts:
                    if p.text:
                        output.append(p.text)
        return "".join(output)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(lambda: asyncio.run(_run())).result()
    else:
        return asyncio.run(_run())



