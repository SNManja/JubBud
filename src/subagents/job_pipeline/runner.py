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
        "max_jobs_per_board": None,
        "delay_between_batches_seconds": 3,
        "delay_between_boards_seconds": 10,
        "max_years_experience": 3,
        "auto_pipeline_execution": True
    }
    if not PIPELINE_CONFIG_PATH.exists():
        return default_config
    try:
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if isinstance(cfg, dict):
                raw_cap = cfg.get("max_jobs_per_board")
                parsed_cap = int(raw_cap) if raw_cap is not None and str(raw_cap).lower() not in ("none", "null") else None
                return {
                    "max_jobs_per_board": parsed_cap,
                    "delay_between_batches_seconds": float(cfg.get("delay_between_batches_seconds", 3)),
                    "delay_between_boards_seconds": float(cfg.get("delay_between_boards_seconds", 10)),
                    "max_years_experience": int(cfg.get("max_years_experience", 3)),
                    "auto_pipeline_execution": bool(cfg.get("auto_pipeline_execution", True))
                }
    except Exception:
        pass
    return default_config


# In-memory cache for candidate jobs returned by board fetchers
LAST_FETCHED_JOBS_CACHE: List[Dict[str, Any]] = []
LAST_FETCHED_STATS_CACHE: Dict[str, Any] = {
    "total_raw": 0,
    "pre_discarded": 0,
    "pre_discarded_summary": []
}

def set_last_fetched_jobs_cache(jobs: List[Dict[str, Any]], total_raw: int = 0, pre_discarded_summary: List[str] = None):
    """Caches candidate jobs and Stage 1/2 fetch stats in memory."""
    global LAST_FETCHED_JOBS_CACHE, LAST_FETCHED_STATS_CACHE
    LAST_FETCHED_JOBS_CACHE = list(jobs)
    summary = list(pre_discarded_summary) if pre_discarded_summary else []
    LAST_FETCHED_STATS_CACHE = {
        "total_raw": total_raw if total_raw > 0 else (len(jobs) + len(summary)),
        "pre_discarded": len(summary),
        "pre_discarded_summary": summary
    }

def get_last_fetched_stats_cache() -> Dict[str, Any]:
    """Returns stored Stage 1/2 acquisition & pre-filter stats."""
    return dict(LAST_FETCHED_STATS_CACHE)

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

    max_retries = 3
    response_text = ""
    for attempt in range(1, max_retries + 1):
        try:
            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    response_text = pool.submit(lambda: asyncio.run(_run())).result()
            else:
                response_text = asyncio.run(_run())
            break
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                time.sleep(15 * attempt)
            else:
                break

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
        Dict containing exact counts across all 6 stages, ranked_jobs, and report_markdown.
    """
    cfg = load_pipeline_config()
    max_jobs_per_board = cfg.get("max_jobs_per_board", 5)
    delay_between_batches = cfg.get("delay_between_batches_seconds", 3)

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
            "report_markdown": "No valid positions were selected for processing."
        }

    if is_full_selection or len(selected_jobs) == len(LAST_FETCHED_JOBS_CACHE):
        total_raw = stats.get("total_raw") or len(selected_jobs)
        pre_discarded_count = stats.get("pre_discarded") or 0
        pre_discarded_summary = stats.get("pre_discarded_summary") or []
    else:
        pre_discarded_count = stats.get("pre_discarded") or 0
        pre_discarded_summary = stats.get("pre_discarded_summary") or []
        total_raw = len(selected_jobs) + pre_discarded_count

    pre_passed_count = len(selected_jobs)

    # Step 1: Parsing / Structuring in memory (Stage 3)
    parsed_jobs = []
    from src.subagents.job_parser.tools import _generate_stable_job_id

    for job in selected_jobs:
        if isinstance(job, dict):
            if job.get("title") == "Posición de Texto Crudo" and job.get("raw_text"):
                pdict = _parse_raw_text_with_adk_parser(job["raw_text"])
            else:
                pdict = job
        elif isinstance(job, str):
            pdict = _parse_raw_text_with_adk_parser(job)
        else:
            continue

        if not pdict.get("id") or str(pdict.get("id")).strip().lower() in ("none", "null", "undefined", ""):
            pdict["id"] = _generate_stable_job_id(
                title=pdict.get("title", ""),
                company=pdict.get("company", ""),
                summary=pdict.get("summary", ""),
                source_page=pdict.get("source_page", ""),
                source_url=pdict.get("source_url", "")
            )

        parsed_jobs.append(pdict)

    # Step 2: Deterministic Post-Parse Filtering (Python / 0 Tokens) (Stage 4)
    valid_jobs = []
    discarded_jobs = []

    for pjob in parsed_jobs:
        passed, reason = evaluate_post_parse_filters(pjob)
        if passed:
            valid_jobs.append(pjob)
        else:
            discarded_jobs.append((pjob, reason))

    post_discarded_count = len(discarded_jobs)

    # Step 2.5: Pre-rank deduplication against existing jobs.json (Dedupe BEFORE Cap)
    from src.subagents.job_ranker.tools import JOBS_FILE_PATH, set_ranking_batch_cache, clear_ranking_batch_cache

    existing_ids = set()
    if JOBS_FILE_PATH.exists():
        try:
            with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                all_stored = json.load(f)
                if not isinstance(all_stored, list):
                    raise ValueError(f"{JOBS_FILE_PATH} no contiene una lista JSON de vacantes.")
                existing_ids = {str(j.get("id")).strip().lower() for j in all_stored if isinstance(j, dict) and j.get("id")}
        except Exception as e:
            err_msg = f"Error al leer/validar {JOBS_FILE_PATH}: {str(e)}"
            report_lines = [
                f"❌ **Error Crítico en Pipeline:**",
                f"- {err_msg}",
                f"- El pipeline fue abortado por seguridad antes de rankear vacantes."
            ]
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
                "report_markdown": "\n".join(report_lines)
            }

    new_jobs = [j for j in valid_jobs if str(j.get("id", "")).strip().lower() not in existing_ids]
    deduped_count = len(valid_jobs) - len(new_jobs)

    # Step 2.8: Optional Capping (applied ONLY to new_jobs)
    capped_jobs = []
    if max_jobs_per_board is not None and max_jobs_per_board > 0 and len(new_jobs) > max_jobs_per_board:
        capped_jobs = new_jobs[max_jobs_per_board:]
        jobs_to_rank = new_jobs[:max_jobs_per_board]
    else:
        jobs_to_rank = new_jobs

    capped_count = len(capped_jobs)

    if not jobs_to_rank:
        report_lines = [
            f"📊 **Reporte de Procesamiento de Tablero:**",
            f"- 📥 **Vacantes obtenidas en crudo (Etapa 1):** {total_raw}",
            f"- 🚫 **Descartadas por filtro pre-parseo duro (Etapa 2):** {pre_discarded_count}",
            f"- 📋 **Vacantes válidas post pre-parseo (Etapa 3):** {pre_passed_count}",
            f"- 🚫 **Descartadas por filtro post-parseo (Etapa 4):** {post_discarded_count}",
            f"- ℹ️ **Omitidas por estar analizadas previamente en jobs.json (Etapa 4):** {deduped_count}",
            f"- ⏸️ **Omitidas por tope configurado por board (Etapa 4):** {capped_count}",
            f"- ⭐ **Vacantes evaluadas y rankeadas con LLM (Etapa 5):** 0",
            f"- 💾 **Vacantes guardadas en jobs.json (Etapa 6):** 0",
            ""
        ]
        if pre_discarded_summary:
            report_lines.append("**Filtros pre-parseo aplicados (Etapa 2):**")
            for item in pre_discarded_summary[:5]:
                report_lines.append(f"  {item}")
            if len(pre_discarded_summary) > 5:
                report_lines.append(f"  ... y {len(pre_discarded_summary) - 5} vacante(s) más.")
            report_lines.append("")
        if discarded_jobs:
            report_lines.append("**Filtros post-parseo aplicados (Etapa 4):**")
            for j, r in discarded_jobs:
                report_lines.append(f"- ❌ **{j.get('title')}**: {r}")

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
            "report_markdown": "\n".join(report_lines)
        }

    # Step 3: Calculate Chunk Size k (Stage 5)
    R = len(jobs_to_rank)
    k = max(1, min(5, math.ceil(R / 4)))
    chunks = [jobs_to_rank[i:i + k] for i in range(0, R, k)]

    # Step 4: Batch Ranking via JobRanker (with transient batch cache lifecycle and inter-batch timer delay)
    candidate_profile = read_candidate_profile()
    ranked_results = []

    for chunk_idx, chunk in enumerate(chunks, start=1):
        if chunk_idx > 1 and delay_between_batches > 0:
            time.sleep(delay_between_batches)
        try:
            set_ranking_batch_cache(chunk)
            ranker_output = _evaluate_batch_chunk_with_adk_ranker(chunk)
            ranked_results.append((chunk, ranker_output))
        finally:
            clear_ranking_batch_cache()

    # Step 5: Reload fully updated job objects from jobs.json
    ranked_hydrated_jobs = []
    if JOBS_FILE_PATH.exists():
        try:
            with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                all_stored = json.load(f)
            stored_by_id = {str(j.get("id")).strip().lower(): j for j in all_stored if isinstance(j, dict) and j.get("id")}

            for vj in jobs_to_rank:
                v_id = str(vj.get("id", "")).strip().lower()
                if v_id in stored_by_id and stored_by_id[v_id].get("status") == "ranked":
                    ranked_hydrated_jobs.append(stored_by_id[v_id])
                else:
                    ranked_hydrated_jobs.append(vj)
        except Exception:
            ranked_hydrated_jobs = jobs_to_rank
    else:
        ranked_hydrated_jobs = jobs_to_rank

    successfully_ranked_count = len(ranked_hydrated_jobs)
    ranking_errors_count = max(0, len(jobs_to_rank) - successfully_ranked_count)

    # Step 6: Generate Consolidated Report
    report_lines = [
        f"📊 **Reporte de Procesamiento de Tablero:**",
        f"- 📥 **Vacantes obtenidas en crudo (Etapa 1):** {total_raw}",
        f"- 🚫 **Descartadas por filtro pre-parseo duro (Etapa 2):** {pre_discarded_count}",
        f"- 📋 **Vacantes válidas post pre-parseo (Etapa 3):** {pre_passed_count}",
        f"- 🚫 **Descartadas por filtro post-parseo (Etapa 4):** {post_discarded_count}",
        f"- ℹ️ **Omitidas por estar analizadas previamente en jobs.json (Etapa 4):** {deduped_count}",
        f"- ⏸️ **Omitidas por tope configurado por board (Etapa 4):** {capped_count}",
        f"- ⭐ **Vacantes evaluadas y rankeadas con LLM (Etapa 5):** {successfully_ranked_count} (Lotes de {k} vacantes)",
        f"- 💾 **Vacantes guardadas en jobs.json (Etapa 6):** {successfully_ranked_count}",
        ""
    ]

    if pre_discarded_summary:
        report_lines.append("**Vacantes descartadas en pre-parseo (Etapa 2):**")
        for item in pre_discarded_summary[:5]:
            report_lines.append(f"  {item}")
        if len(pre_discarded_summary) > 5:
            report_lines.append(f"  ... y {len(pre_discarded_summary) - 5} vacante(s) más.")
        report_lines.append("")

    if discarded_jobs:
        report_lines.append("**Vacantes descartadas en post-parseo (Etapa 4):**")
        for j, r in discarded_jobs:
            report_lines.append(f"- ❌ **{j.get('title')}** en *{j.get('company')}* — *{r}*")
        report_lines.append("")

    if capped_jobs:
        cap_str = f"límite máximo de {max_jobs_per_board}" if max_jobs_per_board is not None else "tope"
        report_lines.append(f"**Vacantes omitidas por superar el {cap_str} por consulta:**")
        for j in capped_jobs:
            report_lines.append(f"- ⏸️ **{j.get('title')}** en *{j.get('company')}*")
        report_lines.append("")

    report_lines.append("**Evaluaciones de Fit (job_ranker_agent):**\n")
    for chunk, output_text in ranked_results:
        report_lines.append(output_text)
        report_lines.append("\n---\n")

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

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(_run())).result()
            else:
                return asyncio.run(_run())
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                time.sleep(15 * attempt)
            else:
                if attempt == max_retries:
                    return f"⚠️ [429 Quota Warning]: Se superó el límite de cuota (15 RPM) al evaluar lote tras {max_retries} reintentos."
                raise e


def _parse_board_indices(scope_str: str, total_boards: int) -> List[int]:
    """
    Parses selection string for 1-indexed board positions (e.g. "1,2,6,8", "del 1 al 5", "1-5", "1, 3, 5-7").
    Returns 0-indexed integer indices to select from sorted_boards list.
    """
    import re
    indices = set()
    sc = scope_str.strip().lower()

    range_matches = list(re.finditer(r'(?:del\s*)?(\d+)\s*(?:a|al|-)\s*(\d+)', sc))
    for rm in range_matches:
        start_idx = int(rm.group(1))
        end_idx = int(rm.group(2))
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        for i in range(start_idx, end_idx + 1):
            if 1 <= i <= total_boards:
                indices.add(i - 1)

    sc_clean = re.sub(r'(?:del\s*)?\d+\s*(?:a|al|-)\s*\d+', '', sc)
    single_digits = re.findall(r'\b\d+\b', sc_clean)
    for d in single_digits:
        val = int(d)
        if 1 <= val <= total_boards:
            indices.add(val - 1)

    return sorted(list(indices))


def filter_boards_by_scope(boards: List[Dict[str, Any]], scope_str: str) -> List[Dict[str, Any]]:
    """
    Filters a list of board objects based on scope criteria:
    - 'unanalyzed' / 'nunca' / 'nuevos': Only boards where last_analyzed is None.
    - 'all' / 'todos': All registered boards.
    - Board index list / ranges (e.g. '1, 2, 6, 8', 'del 1 al 5', '1-5', '1, 3, 5 a 7'): Specific 1-indexed boards.
    - Relative time ('1d', '3d', '12h', '2w', '1m'): Boards not analyzed in relative timeframe (or never analyzed).
    - ISO Date / Timestamp (e.g. '2026-08-01', '2026-08-01T12:00:00'): Boards not analyzed since cutoff date (last_analyzed <= cutoff or never).
    - Directional prefixes: 'after:YYYY-MM-DD' or 'desde:YYYY-MM-DD' (last_analyzed >= cutoff), 'before:YYYY-MM-DD' or 'hasta:YYYY-MM-DD' (last_analyzed <= cutoff).
    """
    import re
    from datetime import datetime, timedelta

    if not boards:
        return []

    sc = scope_str.strip().lower() if scope_str else "unanalyzed"

    if sc in ("unanalyzed", "nunca", "nuevos", "un-analyzed", "sin_analizar"):
        return [b for b in boards if not b.get("last_analyzed")]
    elif sc in ("all", "todos", "todas", "*", "completo"):
        return list(boards)

    is_date_or_time = bool(
        re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', sc) or
        any(sc.startswith(p) for p in ("after:", "desde:", "posterior:", "before:", "hasta:", "anterior:")) or
        re.search(r'\d+\s*(?:[dhwm]|min|día|dias|días|hora|horas|semana|semanas|mes|meses)\b', sc)
    )

    if not is_date_or_time:
        if re.search(r'\b\d+\b', sc) or re.search(r'\d+\s*-\s*\d+', sc):
            selected_indices = _parse_board_indices(sc, len(boards))
            if selected_indices:
                return [boards[i] for i in selected_indices if 0 <= i < len(boards)]

    comparison = "before"
    if sc.startswith("after:") or sc.startswith("desde:") or sc.startswith("posterior:"):
        comparison = "after"
        sc = re.sub(r'^(after:|desde:|posterior:)', '', sc).strip()
    elif sc.startswith("before:") or sc.startswith("hasta:") or sc.startswith("anterior:"):
        comparison = "before"
        sc = re.sub(r'^(before:|hasta:|anterior:)', '', sc).strip()

    now = datetime.now()
    cutoff = None

    # Try parsing as ISO / standard date formats (e.g. 2026-08-01, 2026-08-01T12:00:00, 2026/08/01)
    clean_date = sc.replace("/", "-").replace(" ", "T")
    try:
        if len(clean_date) == 10 and clean_date.count("-") == 2:
            cutoff = datetime.fromisoformat(clean_date + "T00:00:00")
        else:
            cutoff = datetime.fromisoformat(clean_date)
    except ValueError:
        pass

    if cutoff is None:
        if any(w in sc for w in ("dia", "day")) and not re.search(r'\d+[hwm]', sc):
            num_match = re.search(r'(\d+)', sc)
            days = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(days=days)
        elif any(w in sc for w in ("semana", "week")) and not re.search(r'\d+[hdm]', sc):
            num_match = re.search(r'(\d+)', sc)
            weeks = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(weeks=weeks)
        elif any(w in sc for w in ("mes", "month")) and not re.search(r'\d+[hdw]', sc):
            num_match = re.search(r'(\d+)', sc)
            months = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(days=months * 30)
        elif any(w in sc for w in ("hora", "hour")) and not re.search(r'\d+[dwm]', sc):
            num_match = re.search(r'(\d+)', sc)
            hours = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(hours=hours)
        else:
            match = re.search(r'(\d+)\s*([dhwm]|min)?', sc)
            if match:
                num = int(match.group(1))
                unit = match.group(2) or "d"
                if unit == "h":
                    cutoff = now - timedelta(hours=num)
                elif unit == "w":
                    cutoff = now - timedelta(weeks=num)
                elif unit == "m" and "min" not in sc:
                    cutoff = now - timedelta(days=num * 30)
                elif "min" in sc:
                    cutoff = now - timedelta(minutes=num)
                else:
                    cutoff = now - timedelta(days=num)

    if cutoff is None:
        return [b for b in boards if not b.get("last_analyzed")]

    filtered = []
    for b in boards:
        last_an = b.get("last_analyzed")
        if not last_an:
            if comparison == "before":
                filtered.append(b)
        else:
            try:
                dt = datetime.fromisoformat(last_an)
                if comparison == "after" and dt >= cutoff:
                    filtered.append(b)
                elif comparison == "before" and dt <= cutoff:
                    filtered.append(b)
            except Exception:
                if comparison == "before":
                    filtered.append(b)

    return filtered



def run_multi_board_pipeline(scope_str: str = "unanalyzed") -> Dict[str, Any]:
    """
    Executes the automated multi-board sequential pipeline over registered job boards.
    """
    from src.tools.boards import _load_board_urls, _sort_boards_deterministically, get_board_to_analyze

    cfg = load_pipeline_config()
    delay_between_boards = cfg.get("delay_between_boards_seconds", 10)

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
            "report_markdown": "No hay tableros registrados en profile/board_urls.json para analizar."
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
            "report_markdown": f"No hay tableros que coincidan con el criterio de selección '{scope_str}' (ej. sin analizar o vencidos)."
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

    analyzed_board_names = []
    all_newly_ranked_jobs = []

    for idx, board in enumerate(target_boards, start=1):
        if idx > 1 and delay_between_boards > 0:
            time.sleep(delay_between_boards)

        b_name = board.get("name", "Board")
        b_id = board.get("id") or b_name
        analyzed_board_names.append(b_name)

        get_board_to_analyze(b_id)

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

    report_lines = [
        f"🌐 **Reporte Consolidado de Procesamiento Multitablero Automático ({scope_str}):**\n",
        f"- 🏢 **Tableros analizados ({len(analyzed_board_names)}):** {', '.join(analyzed_board_names)}",
        f"- ⏱️ **Timer entre tableros:** {delay_between_boards} segundos",
        f"- 📥 **Total de vacantes obtenidas en crudo (Etapa 1):** {total_raw_sum}",
        f"- 🚫 **Total descartadas por filtro pre-parseo duro (Etapa 2):** {total_pre_discarded_sum}",
        f"- 📋 **Total vacantes válidas post pre-parseo (Etapa 3):** {total_pre_passed_sum}",
        f"- 🚫 **Total descartadas por filtro post-parseo (Etapa 4):** {total_post_discarded_sum}",
        f"- ℹ️ **Total omitidas por estar analizadas previamente en jobs.json (Etapa 4):** {total_deduped_sum}",
        f"- ⏸️ **Total omitidas por tope configurado por board (Etapa 4):** {total_capped_sum}",
        f"- ⭐ **Total vacantes enviadas al LLM ranker (Etapa 5):** {total_sent_to_ranker_sum}",
        f"- 💾 **Total vacantes guardadas en jobs.json (Etapa 6):** {total_passed_sum}",
        ""
    ]

    if top_5_jobs:
        report_lines.append("🏆 **Top 5 Mejores Oportunidades Encontradas en la Corrida:**\n")
        for rank_idx, j in enumerate(top_5_jobs, start=1):
            score = j.get("score", 0)
            title = j.get("title", "Puesto")
            company = j.get("company", "Empresa")
            wmode = j.get("work_mode", "N/A")
            loc = j.get("location", "N/A")
            justification = j.get("justification", "")
            app_method = j.get("application_method") or j.get("source_url") or "Ver ficha"

            report_lines.append(f"{rank_idx}. ⭐ **{score}/100** — **{title}** en *{company}* ({wmode} - {loc})")
            if justification:
                brief_just = justification.split("\n")[0][:180]
                report_lines.append(f"   - *Fit:* {brief_just}...")
            report_lines.append(f"   - *Postulación:* {app_method}\n")
    else:
        report_lines.append("Ninguna posición superó el umbral de filtrado en esta corrida multitablero.")

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
        "report_markdown": "\n".join(report_lines)
    }
