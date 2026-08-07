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
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from src.tools.queries import evaluate_post_parse_filters
from src.subagents.job_ranker.tools import read_candidate_profile, save_ranked_jobs_batch

ROOT_DIR = Path(__file__).resolve().parents[3]
PIPELINE_CONFIG_PATH = ROOT_DIR / "profile" / "pipeline_config.json"


def load_pipeline_config() -> Dict[str, Any]:
    """Reads configuration settings from profile/pipeline_config.json with safe fallbacks."""
    default_config = {
        "max_jobs_per_board": 5,
        "delay_between_batches_seconds": 3,
        "auto_pipeline_execution": True
    }
    if not PIPELINE_CONFIG_PATH.exists():
        return default_config
    try:
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if isinstance(cfg, dict):
                return {
                    "max_jobs_per_board": int(cfg.get("max_jobs_per_board", 5)),
                    "delay_between_batches_seconds": float(cfg.get("delay_between_batches_seconds", 3)),
                    "auto_pipeline_execution": bool(cfg.get("auto_pipeline_execution", True))
                }
    except Exception:
        pass
    return default_config


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


def _parse_raw_text_with_adk_parser(raw_text: str) -> Dict[str, Any]:
    """
    Invokes job_parser_agent via Google ADK InMemoryRunner to extract structured fields
    from a raw unparsed job posting text.
    """
    import asyncio
    import json
    import concurrent.futures
    import re
    from google.genai import types
    from google.adk.runners import InMemoryRunner
    from src.subagents.job_parser.job_parser import job_parser_agent
    from src.subagents.job_parser.tools import build_unified_job_dict

    runner = InMemoryRunner(agent=job_parser_agent)
    session = runner.session_service.create_session_sync(user_id="jobbud_user", app_name=runner.app_name)

    prompt = (
        f"Analiza la siguiente oferta de empleo y guárdala estructurada usando save_job_json:\n\n"
        f"{raw_text}"
    )

    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    captured_args = {}

    async def _run():
        nonlocal captured_args
        output = []
        async for event in runner.run_async(user_id="jobbud_user", session_id=session.id, new_message=message):
            if hasattr(event, "content") and event.content and event.content.parts:
                for p in event.content.parts:
                    if hasattr(p, "function_call") and p.function_call and p.function_call.name == "save_job_json":
                        try:
                            captured_args = dict(p.function_call.args)
                        except Exception:
                            pass
                    if p.text:
                        output.append(p.text)
        return "".join(output)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            response_text = pool.submit(lambda: asyncio.run(_run())).result()
    else:
        response_text = asyncio.run(_run())

    if captured_args and captured_args.get("title"):
        return build_unified_job_dict(
            title=captured_args.get("title", "Posición de Texto Crudo"),
            company=captured_args.get("company", "Not specified"),
            location=captured_args.get("location", "Not specified"),
            work_mode=captured_args.get("work_mode", "Not specified"),
            commitment=captured_args.get("commitment", "Not specified"),
            salary_range=captured_args.get("salary_range", "Not specified"),
            key_technologies=captured_args.get("key_technologies", []) if isinstance(captured_args.get("key_technologies"), list) else [],
            main_requirements=captured_args.get("main_requirements", []) if isinstance(captured_args.get("main_requirements"), list) else [],
            summary=captured_args.get("summary", raw_text[:300]),
            raw_text=raw_text,
            language=captured_args.get("language", "es"),
            source_page=captured_args.get("source_page", "Manual"),
            source_url=captured_args.get("source_url"),
            department=captured_args.get("department"),
            seniority=captured_args.get("seniority"),
            application_method=captured_args.get("application_method")
        )

    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        try:
            p = json.loads(json_match.group(0))
            return build_unified_job_dict(
                title=p.get("title", "Posición de Texto Crudo"),
                company=p.get("company", "Not specified"),
                location=p.get("location", "Not specified"),
                work_mode=p.get("work_mode", "Not specified"),
                commitment=p.get("commitment", "Not specified"),
                salary_range=p.get("salary_range", "Not specified"),
                key_technologies=p.get("key_technologies", []) if isinstance(p.get("key_technologies"), list) else [],
                main_requirements=p.get("main_requirements", []) if isinstance(p.get("main_requirements"), list) else [],
                summary=p.get("summary", raw_text[:300]),
                raw_text=raw_text,
                language=p.get("language", "es"),
                source_page=p.get("source_page", "Manual"),
                source_url=p.get("source_url"),
                department=p.get("department"),
                seniority=p.get("seniority"),
                application_method=p.get("application_method")
            )
        except Exception:
            pass

    return build_unified_job_dict(
        title="Posición de Texto Crudo",
        company="Not specified",
        location="Not specified",
        work_mode="Not specified",
        commitment="Not specified",
        salary_range="Not specified",
        key_technologies=[],
        main_requirements=[],
        summary=raw_text[:300],
        raw_text=raw_text,
        language="es",
        source_page="Manual"
    )


def run_job_processing_pipeline(selected_jobs: Any) -> Dict[str, Any]:
    """
    Executes the deterministic sequential job processing pipeline over selected jobs.

    Args:
        selected_jobs: Selection string (e.g. "1, 3") or List of job dicts.

    Returns:
        Dict containing total_processed, passed_count, discarded_count, ranked_jobs, and report_markdown.
    """
    cfg = load_pipeline_config()
    max_jobs_per_board = cfg.get("max_jobs_per_board", 5)
    delay_between_batches = cfg.get("delay_between_batches_seconds", 3)

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
            if job.get("title") == "Posición de Texto Crudo" and job.get("raw_text"):
                parsed_jobs.append(_parse_raw_text_with_adk_parser(job["raw_text"]))
            else:
                parsed_jobs.append(job)
        elif isinstance(job, str):
            parsed_jobs.append(_parse_raw_text_with_adk_parser(job))

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
            f"📋 **Resultados del Procesamiento ({len(parsed_jobs)} observadas):**\n"
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

    # Step 2.5: Apply max_jobs_per_board cap
    capped_jobs = []
    if max_jobs_per_board > 0 and len(valid_jobs) > max_jobs_per_board:
        capped_jobs = valid_jobs[max_jobs_per_board:]
        valid_jobs = valid_jobs[:max_jobs_per_board]

    # Step 3: Calculate Chunk Size k
    R = len(valid_jobs)
    k = max(1, min(5, math.ceil(R / 4)))
    chunks = [valid_jobs[i:i + k] for i in range(0, R, k)]

    # Step 4: Batch Ranking via JobRanker (with inter-batch timer delay)
    candidate_profile = read_candidate_profile()
    ranked_results = []

    for chunk_idx, chunk in enumerate(chunks, start=1):
        if chunk_idx > 1 and delay_between_batches > 0:
            time.sleep(delay_between_batches)
        ranker_output = _evaluate_batch_chunk_with_adk_ranker(chunk)
        ranked_results.append((chunk, ranker_output))

    # Step 6: Generate Consolidated Report
    report_lines = [
        f"📊 **Reporte de Procesamiento Final ({len(parsed_jobs)} vacantes observadas):**",
        f"- 🚫 **Descartadas por filtros (roles/seniority/ubicación):** {len(discarded_jobs)}",
    ]
    if capped_jobs:
        report_lines.append(f"- ⏸️ **Omitidas por superar el tope configurado por board ({max_jobs_per_board}):** {len(capped_jobs)}")

    report_lines.extend([
        f"- ⭐ **Posiciones evaluadas y rankeadas con job_ranker_agent:** {len(valid_jobs)} (Lotes de {k} vacantes)",
        ""
    ])

    if discarded_jobs:
        report_lines.append("**Vacantes descartadas post-parseo:**")
        for j, r in discarded_jobs:
            report_lines.append(f"- ❌ **{j.get('title')}** en *{j.get('company')}* — *{r}*")
        report_lines.append("")

    if capped_jobs:
        report_lines.append(f"**Vacantes omitidas por superar el límite máximo de {max_jobs_per_board} por consulta:**")
        for j in capped_jobs:
            report_lines.append(f"- ⏸️ **{j.get('title')}** en *{j.get('company')}*")
        report_lines.append("")

    report_lines.append("**Evaluaciones de Fit (job_ranker_agent):**\n")
    for chunk, output_text in ranked_results:
        report_lines.append(output_text)
        report_lines.append("\n---\n")

    return {
        "total_processed": len(parsed_jobs),
        "passed_count": len(valid_jobs),
        "discarded_count": len(discarded_jobs),
        "capped_count": len(capped_jobs),
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



