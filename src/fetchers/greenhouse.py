"""
Greenhouse API fetcher for JobBud.
Fetches single job postings or full job boards via official Greenhouse Public API.
Returns normalized List[JobDict] (0 LLM tokens spent) and provides the agent tool.
"""

import html
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple, Optional

from src.fetchers.base import compress_job_text, extract_technologies_from_text
from src.subagents.job_parser.tools import build_unified_job_dict, extract_commitment


def parse_greenhouse_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts (board_token, job_id) from a Greenhouse URL.

    Args:
        url: Greenhouse job post or job board URL.

    Returns:
        Tuple of (board_token, job_id). job_id may be None for board-level URLs.
    """
    cleaned_url = url.strip()

    # 1. Direct API endpoint match: e.g. boards-api.greenhouse.io/v1/boards/appsflyer/jobs/123456 or /jobs
    api_match = re.search(
        r"greenhouse\.io/v1/boards/([^/?&]+)(?:/jobs/(\d+)|/jobs)?",
        cleaned_url,
        re.IGNORECASE,
    )
    if api_match:
        return api_match.group(1), api_match.group(2)

    # 2. Query parameters with explicit for & token/gh_jid
    for_match = re.search(r"[?&]for=([^&]+)", cleaned_url, re.IGNORECASE)
    token_match = re.search(
        r"[?&](?:token|gh_jid|job_id)=(\d+)", cleaned_url, re.IGNORECASE
    )
    if for_match and token_match:
        return for_match.group(1), token_match.group(1)

    # 3. Path match with job ID: e.g. job-boards.greenhouse.io/canonical/jobs/5647382
    path_job_match = re.search(
        r"greenhouse\.io/([^/?]+)/(?:jobs|positions)/(\d+)",
        cleaned_url,
        re.IGNORECASE,
    )
    if path_job_match:
        return path_job_match.group(1), path_job_match.group(2)

    # 4. Path match with board token: e.g. boards.greenhouse.io/canonical
    board_path_match = re.search(r"greenhouse\.io/([^/?]+)", cleaned_url, re.IGNORECASE)
    if board_path_match and board_path_match.group(1).lower() not in (
        "embed",
        "v1",
        "api",
        "jobs",
    ):
        board_token = board_path_match.group(1)
        job_id = token_match.group(1) if token_match else None
        return board_token, job_id

    # 5. Fallback for token without explicit board in path
    if token_match and for_match:
        return for_match.group(1), token_match.group(1)

    return None, None


def fetch_greenhouse_jobs(url: str) -> List[Dict[str, Any]]:
    """
    Fetches job details or board listings from Greenhouse using the official Greenhouse Public Board API.

    Args:
        url: Greenhouse job posting URL or job board URL.

    Returns:
        List of normalized JobDict objects (single element if specific job_id, multiple if board).
    """
    cleaned_url = url.strip()
    board_token, job_id = parse_greenhouse_url(cleaned_url)

    if not board_token:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    # Case A: Fetch single job posting by job_id -> returns List with 1 JobDict
    if job_id:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?content=true"
        try:
            resp = requests.get(api_url, headers=headers, timeout=12)
            if resp.status_code != 200:
                return []

            data = resp.json()
            title = data.get("title", "Unknown Title")
            location_info = data.get("location", {})
            location_name = (
                location_info.get("name", "Not specified")
                if isinstance(location_info, dict)
                else str(location_info)
            )
            absolute_url = data.get("absolute_url", cleaned_url)
            departments = ", ".join(
                d.get("name", "") for d in data.get("departments", []) if d.get("name")
            )

            raw_content = data.get("content", "")
            decoded_html = html.unescape(raw_content)
            soup = BeautifulSoup(decoded_html, "html.parser")
            clean_desc = compress_job_text(soup.get_text("\n", strip=True))

            full_lower = f"{title}\n{location_name}\n{clean_desc}".lower()
            work_mode = (
                "Remote"
                if "remote" in full_lower
                else (
                    "Hybrid"
                    if "hybrid" in full_lower or "híbrido" in full_lower
                    else (
                        "On-site"
                        if "on-site" in full_lower or "onsite" in full_lower
                        else "Not specified"
                    )
                )
            )
            commitment = extract_commitment(title, clean_desc, None)
            found_techs = extract_technologies_from_text(f"{title}\n{clean_desc}")

            job_dict = build_unified_job_dict(
                title=title,
                company=board_token,
                location=location_name,
                work_mode=work_mode,
                commitment=commitment,
                department=departments,
                salary_range="Not specified",
                key_technologies=found_techs,
                main_requirements=[],
                summary=clean_desc[:300],
                raw_text=clean_desc,
                language="en",
                source_page=f"Greenhouse ({board_token})",
                source_url=absolute_url,
                job_id=f"greenhouse_{board_token}_{job_id}",
                status="new",
            )
            return [job_dict]
        except Exception:
            return []

    # Case B: Fetch board listing -> returns List of JobDicts
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        jobs = data.get("jobs", [])
        if not jobs:
            return []

        job_dicts: List[Dict[str, Any]] = []
        for job in jobs:
            j_id = str(job.get("id"))
            j_title = job.get("title", "Untitled")
            j_loc = (
                job.get("location", {}).get("name", "N/A")
                if isinstance(job.get("location"), dict)
                else "N/A"
            )
            j_url = job.get("absolute_url", cleaned_url)
            j_deps = ", ".join(
                d.get("name", "") for d in job.get("departments", []) if d.get("name")
            )

            raw_content = job.get("content", "")
            decoded_html = html.unescape(raw_content)
            soup = BeautifulSoup(decoded_html, "html.parser")
            clean_desc = compress_job_text(soup.get_text("\n", strip=True))

            full_lower = f"{j_title}\n{j_loc}\n{clean_desc}".lower()
            work_mode = (
                "Remote"
                if "remote" in full_lower
                else (
                    "Hybrid"
                    if "hybrid" in full_lower or "híbrido" in full_lower
                    else (
                        "On-site"
                        if "on-site" in full_lower or "onsite" in full_lower
                        else "Not specified"
                    )
                )
            )
            commitment = extract_commitment(j_title, clean_desc, None)
            found_techs = extract_technologies_from_text(f"{j_title}\n{clean_desc}")

            summary_paras = [
                p.strip() for p in clean_desc.split("\n\n") if len(p.strip()) > 30
            ]
            summary = summary_paras[0] if summary_paras else clean_desc[:200]

            udict = build_unified_job_dict(
                title=j_title,
                company=board_token,
                location=j_loc,
                work_mode=work_mode,
                commitment=commitment,
                department=j_deps,
                salary_range="Not specified",
                key_technologies=found_techs,
                main_requirements=[],
                summary=summary[:300],
                raw_text=clean_desc,
                language="en",
                source_page=f"Greenhouse ({board_token})",
                source_url=j_url,
                job_id=f"greenhouse_{board_token}_{j_id}",
                status="new",
            )
            job_dicts.append(udict)

        return job_dicts
    except Exception:
        return []


def fetch_greenhouse_job_content(url: str) -> str:
    """
    Agent tool: Fetches job details or job board listings from Greenhouse using the official Greenhouse API,
    applies Stage 2 hard pre-filters, and stores candidates in memory cache.

    Args:
        url: A Greenhouse job posting URL or job board URL.

    Returns:
        Formatted text summary and candidates listing for user interaction.
    """
    cleaned_url = url.strip()
    board_token, job_id = parse_greenhouse_url(cleaned_url)

    if not board_token:
        return (
            "Error: Could not extract a valid Greenhouse board token or job ID from the provided URL. "
            "Please check the URL or paste the job description text directly."
        )

    jobs = fetch_greenhouse_jobs(cleaned_url)
    if not jobs:
        if job_id:
            return f"Error: Job ID '{job_id}' was not found on Greenhouse board '{board_token}' or could not be retrieved."
        return f"No active job postings found on Greenhouse board '{board_token}'."

    from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache

    # If single job
    if job_id and len(jobs) == 1:
        job = jobs[0]
        set_last_fetched_jobs_cache(jobs, total_raw=1, pre_discarded_summary=[])
        return (
            f"Source Page: Greenhouse\n"
            f"Source URL: {job.get('source_url', cleaned_url)}\n"
            f"Greenhouse Job ID: {job_id}\n"
            f"Board Token: {board_token}\n"
            f"Title: {job.get('title')}\n"
            f"Company / Board: {job.get('company')}\n"
            f"Location: {job.get('location')}\n"
            f"Department: {job.get('department')}\n\n"
            f"Job Description:\n{job.get('raw_text')}"
        )

    # If board listing: Apply Stage 2 hard pre-filters
    from src.tools.queries import load_blacklist_terms, filter_job_by_location

    terms = load_blacklist_terms()
    retained_job_dicts: List[Dict[str, Any]] = []
    discarded_summary: List[str] = []

    for job in jobs:
        j_id = job.get("id", "gh_job")
        j_title = job.get("title", "Untitled")
        j_loc = job.get("location", "N/A")
        j_deps = job.get("department", "")

        # 1. Location pre-filter
        pre_loc_passed, pre_loc_reason = filter_job_by_location(job)
        if not pre_loc_passed:
            discarded_summary.append(
                f"- **{j_title}** (ID: {j_id}, Ubicación: {j_loc}) — *{pre_loc_reason}*"
            )
            continue

        # 2. Blacklist term check
        title_and_dept = f"{j_title} {j_deps}".lower()
        matched_term = None
        for term in terms:
            if re.search(r"\b" + re.escape(term.lower()) + r"\b", title_and_dept):
                matched_term = term
                break

        if matched_term:
            discarded_summary.append(
                f"- **{j_title}** (ID: {j_id}, Área: {j_deps or 'N/A'}) — *Filtrado por: '{matched_term}'*"
            )
        else:
            retained_job_dicts.append(job)

    set_last_fetched_jobs_cache(
        retained_job_dicts,
        total_raw=len(jobs),
        pre_discarded_summary=discarded_summary,
    )

    if not retained_job_dicts:
        return (
            f"📊 **Estadísticas de Procesamiento (Greenhouse: {board_token})**\n"
            f"- 🔍 **Total de vacantes observadas:** {len(jobs)}\n"
            f"- 🚫 **Omitidas por filtros automáticos (blacklist / ubicación):** {len(discarded_summary)}\n"
            f"- 📋 **Vacantes conservadas:** 0\n\n"
            f"Ninguna posición superó los filtros iniciales."
        )

    report_parts = [
        f"📊 **Estadísticas de Procesamiento (Greenhouse: {board_token})**",
        f"- 🔍 **Total de vacantes observadas:** {len(jobs)}",
        f"- 🚫 **Omitidas por filtros automáticos (blacklist / ubicación):** {len(discarded_summary)}",
        f"- 📋 **Vacantes conservadas que superaron los filtros:** {len(retained_job_dicts)}",
        f"\n❓ **Confirmación Requerida:**",
        f"Se encontraron **{len(retained_job_dicts)} vacante(s)** que superaron los filtros deterministas. Por favor, confirma cuáles deseas evaluar y rankear con el LLM (puedes responder con números como '1, 3', 'todas' o 'ninguna'):",
        "",
    ]

    for idx, udict in enumerate(retained_job_dicts, start=1):
        report_parts.append(
            f"{idx}. **[{udict['id']}]** {udict['title']} en *{udict['company']}* — "
            f"Ubicación: {udict['location']} | Modalidad: `{udict['work_mode']}`"
        )

    if discarded_summary:
        report_parts.append(
            f"\n🚫 **Resumen de vacantes filtradas automáticamente ({len(discarded_summary)}):**"
        )
        report_parts.extend(discarded_summary[:5])
        if len(discarded_summary) > 5:
            report_parts.append(f"... y {len(discarded_summary) - 5} vacante(s) filtradas más.")

    report_parts.append(
        "\n⛔ **NO PROCEDER AL RANKING SIN CONFIRMACIÓN:** El orquestador debe mostrar esta lista al usuario y esperar su elección explícita antes de invocar a `job_ranker_agent`."
    )

    return "\n".join(report_parts)
