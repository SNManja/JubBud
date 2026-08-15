"""
ADK subagent invocation adapters for JobBud.
Encapsulates asynchronous Google ADK runner loops, retry logic, and quota error handling.
"""

import asyncio
import concurrent.futures
import json
import re
import time
from typing import List, Dict, Any, Optional

from google.genai import types
from google.adk.runners import InMemoryRunner

from src.subagents.job_parser.job_parser import job_parser_agent
from src.subagents.job_parser.tools import build_unified_job_dict
from src.subagents.job_ranker.job_ranker import job_ranker_agent


def _run_coroutine_sync(coro_fn, max_retries: int = 3, retry_delay_factor: float = 15.0):
    """
    Executes an async coroutine synchronously, handling running event loops
    and applying exponential backoff on 429/RESOURCE_EXHAUSTED errors.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    for attempt in range(1, max_retries + 1):
        try:
            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(coro_fn())).result()
            else:
                return asyncio.run(coro_fn())
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                time.sleep(retry_delay_factor * attempt)
            else:
                if attempt == max_retries and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                    return f"⚠️ [429 Quota Warning]: Se superó el límite de cuota (15 RPM) tras {max_retries} reintentos."
                raise e


def parse_raw_text_with_adk(raw_text: str) -> Dict[str, Any]:
    """
    Invokes job_parser_agent via Google ADK InMemoryRunner to extract structured fields
    from a raw unparsed job posting text.
    """
    runner = InMemoryRunner(agent=job_parser_agent)
    session = runner.session_service.create_session_sync(
        user_id="jobbud_user", app_name=runner.app_name
    )

    prompt = (
        f"Analiza la siguiente oferta de empleo y guárdala estructurada usando save_job_json:\n\n"
        f"{raw_text}"
    )
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    captured_args: Dict[str, Any] = {}

    async def _async_run():
        nonlocal captured_args
        output = []
        async for event in runner.run_async(
            user_id="jobbud_user", session_id=session.id, new_message=message
        ):
            if hasattr(event, "content") and event.content and event.content.parts:
                for p in event.content.parts:
                    if (
                        hasattr(p, "function_call")
                        and p.function_call
                        and p.function_call.name == "save_job_json"
                    ):
                        try:
                            captured_args = dict(p.function_call.args)
                        except Exception:
                            pass
                    if p.text:
                        output.append(p.text)
        return "".join(output)

    try:
        response_text = _run_coroutine_sync(_async_run) or ""
    except Exception:
        response_text = ""

    # 1. Prefer function call arguments captured from save_job_json
    if captured_args and captured_args.get("title"):
        return build_unified_job_dict(
            title=captured_args.get("title", "Posición de Texto Crudo"),
            company=captured_args.get("company", "Not specified"),
            location=captured_args.get("location", "Not specified"),
            work_mode=captured_args.get("work_mode", "Not specified"),
            commitment=captured_args.get("commitment", "Not specified"),
            salary_range=captured_args.get("salary_range", "Not specified"),
            key_technologies=(
                captured_args.get("key_technologies", [])
                if isinstance(captured_args.get("key_technologies"), list)
                else []
            ),
            main_requirements=(
                captured_args.get("main_requirements", [])
                if isinstance(captured_args.get("main_requirements"), list)
                else []
            ),
            summary=captured_args.get("summary", raw_text[:300]),
            raw_text=raw_text,
            language=captured_args.get("language", "es"),
            source_page=captured_args.get("source_page", "Manual"),
            source_url=captured_args.get("source_url"),
            department=captured_args.get("department"),
            seniority=captured_args.get("seniority"),
            application_method=captured_args.get("application_method"),
        )

    # 2. Fallback: Parse embedded JSON from agent response text
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
                key_technologies=(
                    p.get("key_technologies", [])
                    if isinstance(p.get("key_technologies"), list)
                    else []
                ),
                main_requirements=(
                    p.get("main_requirements", [])
                    if isinstance(p.get("main_requirements"), list)
                    else []
                ),
                summary=p.get("summary", raw_text[:300]),
                raw_text=raw_text,
                language=p.get("language", "es"),
                source_page=p.get("source_page", "Manual"),
                source_url=p.get("source_url"),
                department=p.get("department"),
                seniority=p.get("seniority"),
                application_method=p.get("application_method"),
            )
        except Exception:
            pass

    # 3. Default fallback for unparseable raw text
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
        source_page="Manual",
    )


def evaluate_ranking_chunk_with_adk(chunk: List[Dict[str, Any]]) -> str:
    """
    Invokes job_ranker_agent via Google ADK InMemoryRunner to evaluate a batch chunk
    of jobs against candidate_profile.md.
    """
    runner = InMemoryRunner(agent=job_ranker_agent)
    session = runner.session_service.create_session_sync(
        user_id="jobbud_user", app_name=runner.app_name
    )

    prompt = (
        f"Evalúa la compatibilidad (fit) de las siguientes vacantes (lote) contra candidate_profile.md (usa read_candidate_profile) "
        f"y guarda los resultados en jobs.json usando save_ranked_jobs_batch:\n\n"
        f"{json.dumps(chunk, ensure_ascii=False, indent=2)}"
    )
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    async def _async_run():
        output = []
        async for event in runner.run_async(
            user_id="jobbud_user", session_id=session.id, new_message=message
        ):
            if hasattr(event, "content") and event.content and event.content.parts:
                for p in event.content.parts:
                    if p.text:
                        output.append(p.text)
        return "".join(output)

    result = _run_coroutine_sync(_async_run)
    return str(result) if result else ""
