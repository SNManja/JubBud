"""
Ashby Public Job Board API fetcher for JobBud.
Fetches single job postings or full job boards via official Ashby Public Job Board API.
Returns normalized List[JobDict] (0 LLM tokens spent) and provides the agent tool.
"""

import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from src.fetchers.base import compress_job_text, extract_technologies_from_text
from src.subagents.job_parser.tools import build_unified_job_dict


def parse_ashby_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts (board_name, job_uuid) from an Ashby URL.

    Args:
        url: Ashby job post or job board URL.

    Returns:
        Tuple of (board_name, job_uuid). job_uuid is None for board-level URLs.
    """
    cleaned_url = url.strip()

    # 1. Direct API endpoint match: e.g. api.ashbyhq.com/posting-api/job-board/openai
    api_match = re.search(
        r"ashbyhq\.com/posting-api/job-board/([^/?&]+)",
        cleaned_url,
        re.IGNORECASE,
    )
    if api_match:
        return api_match.group(1), None

    # 2. Path match with UUID: e.g. jobs.ashbyhq.com/company/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3 or /apply
    job_match = re.search(
        r"ashbyhq\.com/([^/?&]+)/([a-f0-9\-]{36})(?:/.*)?",
        cleaned_url,
        re.IGNORECASE,
    )
    if job_match:
        return job_match.group(1), job_match.group(2)

    # 3. Path match with board name: e.g. jobs.ashbyhq.com/company or jobs.ashbyhq.com/company/
    board_match = re.search(
        r"ashbyhq\.com/([^/?&]+)",
        cleaned_url,
        re.IGNORECASE,
    )
    if board_match:
        board_name = board_match.group(1)
        if board_name.lower() not in ("posting-api", "api", "embed"):
            # Check for query param job_id / ashby_jid
            query_uuid = re.search(
                r"[?&](?:ashby_jid|job_id|id)=([a-f0-9\-]{36})",
                cleaned_url,
                re.IGNORECASE,
            )
            job_uuid = query_uuid.group(1) if query_uuid else None
            return board_name, job_uuid

    return None, None


def _detect_language_deterministic(text: str) -> str:
    """
    Simple deterministic language detection based on frequency of common Spanish vs English stop words.
    0 LLM tokens spent.
    """
    sample = (text or "")[:1500].lower()
    spanish_markers = len(re.findall(r"\b(de|en|para|con|por|requisitos|experiencia|trabajo|puesto|conocimientos|modalidad|remoto|híbrido|estudiante|carrera|años)\b", sample))
    english_markers = len(re.findall(r"\b(the|and|in|with|for|requirements|experience|skills|role|responsibilities|job|work|years|team|company)\b", sample))

    if spanish_markers > english_markers and spanish_markers >= 3:
        return "es"
    return "en"


def _normalize_work_mode(workplace_type: Optional[str], is_remote: Optional[bool]) -> str:
    """Normalizes Ashby workplace type and remote flag to JobBud standard."""
    wt_clean = str(workplace_type or "").strip().lower()
    if wt_clean in ("onsite", "on-site", "on_site"):
        return "On-site"
    elif wt_clean == "remote":
        return "Remote"
    elif wt_clean in ("hybrid", "híbrido", "hibrido"):
        return "Hybrid"
    elif is_remote is True:
        return "Remote"
    elif is_remote is False and workplace_type:
        return "On-site"
    return "Not specified"


def _normalize_commitment(employment_type: Optional[str]) -> str:
    """Normalizes Ashby employment type to JobBud standard."""
    et_clean = str(employment_type or "").strip().lower()
    if et_clean in ("fulltime", "full-time", "full_time"):
        return "Full-time"
    elif et_clean in ("parttime", "part-time", "part_time"):
        return "Part-time"
    elif et_clean in ("intern", "internship", "pasantia", "pasantía"):
        return "Internship"
    elif et_clean == "contract":
        return "Contract"
    elif et_clean == "temporary":
        return "Temporary"
    return "Not specified"


def fetch_ashby_jobs(url: str) -> List[Dict[str, Any]]:
    """
    Fetches job details or full board listings from Ashby using the official Public Job Board API.

    Args:
        url: Ashby job posting URL or job board URL.

    Returns:
        List of normalized JobDict objects (single element if specific job UUID, multiple if board).
    """
    cleaned_url = url.strip()
    board_name, target_uuid = parse_ashby_url(cleaned_url)

    if not board_name:
        return []

    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    try:
        resp = requests.get(api_url, headers=headers, timeout=12)
        if resp.status_code != 200:
            return []

        data = resp.json()
        raw_jobs = data.get("jobs", [])
        if not raw_jobs or not isinstance(raw_jobs, list):
            return []

        normalized_jobs: List[Dict[str, Any]] = []

        for item in raw_jobs:
            job_id_raw = item.get("id")
            job_url = item.get("jobUrl", "")
            apply_url = item.get("applyUrl", "")

            # Extract job UUID
            job_uuid = job_id_raw
            if not job_uuid and job_url:
                uuid_match = re.search(r"([a-f0-9\-]{36})", job_url, re.IGNORECASE)
                if uuid_match:
                    job_uuid = uuid_match.group(1)

            # If a specific single job UUID was requested, filter down strictly to it
            if target_uuid:
                if not job_uuid or job_uuid.lower() != target_uuid.lower():
                    continue

            title = item.get("title", "Untitled").strip()

            # Consolidate primary location and secondaryLocations
            primary_loc = item.get("location")
            sec_locs = [
                s.get("location") for s in item.get("secondaryLocations", [])
                if isinstance(s, dict) and s.get("location")
            ]
            all_locs = []
            if primary_loc:
                all_locs.append(str(primary_loc).strip())
            for sec in sec_locs:
                sec_str = str(sec).strip()
                if sec_str and sec_str not in all_locs:
                    all_locs.append(sec_str)
            location = "; ".join(all_locs) if all_locs else "Not specified"

            # Department & Team
            department = item.get("department")
            team = item.get("team")
            if department and team and str(team).strip().lower() != str(department).strip().lower():
                full_dept = f"{str(department).strip()} - {str(team).strip()}"
            else:
                full_dept = str(department or team or "Not specified").strip()

            # Work Mode & Commitment
            work_mode = _normalize_work_mode(item.get("workplaceType"), item.get("isRemote"))
            commitment = _normalize_commitment(item.get("employmentType"))

            # Description plain & text compression
            desc_plain = item.get("descriptionPlain", "")
            clean_desc = compress_job_text(desc_plain) if desc_plain else title

            # Compensation
            comp_obj = item.get("compensation", {})
            salary_range = "Not specified"
            if isinstance(comp_obj, dict):
                salary_summary = (
                    comp_obj.get("scrapeableCompensationSalarySummary")
                    or comp_obj.get("compensationTierSummary")
                )
                if salary_summary and str(salary_summary).strip():
                    salary_range = str(salary_summary).strip()

            # Technologies & Language
            found_techs = extract_technologies_from_text(f"{title}\n{clean_desc}")
            lang = _detect_language_deterministic(f"{title}\n{clean_desc}")

            # Canonical ID and Application Method
            stable_id = f"ashby_{board_name.lower()}_{job_uuid}" if job_uuid else f"ashby_{board_name.lower()}"
            source_url = job_url or cleaned_url
            app_method = f"Postulación web en: {apply_url or job_url or source_url}"

            job_dict = build_unified_job_dict(
                title=title,
                company=board_name,
                location=location,
                work_mode=work_mode,
                commitment=commitment,
                department=full_dept,
                salary_range=salary_range,
                key_technologies=found_techs,
                main_requirements=[],
                summary=clean_desc[:300],
                raw_text=clean_desc,
                language=lang,
                source_page=f"Ashby ({board_name})",
                source_url=source_url,
                job_id=stable_id,
                application_method=app_method,
                status="new",
            )
            normalized_jobs.append(job_dict)

            # If target_uuid was matched, break early
            if target_uuid and len(normalized_jobs) == 1:
                break

        return normalized_jobs

    except Exception:
        return []


def fetch_ashby_job_content(url: str) -> str:
    """
    Agent tool: Fetches job descriptions or board listings from Ashby Public Job Board API,
    applies hard pre-filters (Stage 2), and sets the in-memory candidate cache.

    Args:
        url: Ashby job posting URL or job board URL.

    Returns:
        Formatted text summary and candidates listing for user interaction.
    """
    cleaned_url = url.strip()
    board_name, job_uuid = parse_ashby_url(cleaned_url)

    if not board_name:
        return (
            "Error: Could not extract a valid Ashby board name or job UUID from the provided URL. "
            "Please check the URL or paste the job description text directly."
        )

    jobs = fetch_ashby_jobs(cleaned_url)
    if not jobs:
        if job_uuid:
            return f"Error: Job UUID '{job_uuid}' was not found on Ashby board '{board_name}' or could not be retrieved."
        return f"No active job postings found on Ashby board '{board_name}'."

    # Single job posting view
    if job_uuid and len(jobs) == 1:
        job = jobs[0]
        from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache

        set_last_fetched_jobs_cache(jobs, total_raw=1, pre_discarded_summary=[])
        return (
            f"Source Page: Ashby ({board_name})\n"
            f"Source URL: {job.get('source_url', cleaned_url)}\n"
            f"Ashby Job UUID: {job_uuid}\n"
            f"Board Name: {board_name}\n"
            f"Title: {job.get('title')}\n"
            f"Company / Board: {job.get('company')}\n"
            f"Location: {job.get('location')}\n"
            f"Work Mode: {job.get('work_mode')}\n"
            f"Commitment: {job.get('commitment')}\n"
            f"Department: {job.get('department')}\n"
            f"Salary: {job.get('salary_range')}\n\n"
            f"Job Description:\n{job.get('raw_text')}"
        )

    # Board listing: Apply Stage 2 hard pre-filters
    from src.tools.queries import load_blacklist_terms, filter_job_by_location

    terms = load_blacklist_terms()
    retained_job_dicts: List[Dict[str, Any]] = []
    discarded_summary: List[str] = []

    for job in jobs:
        j_id = job.get("id", "ashby_job")
        j_title = job.get("title", "Untitled")
        j_dept = job.get("department", "")

        # 1. Check title/department against pre-parse blacklist terms
        title_and_dept = f"{j_title} {j_dept}".lower()
        matched_term = None
        for term in terms:
            if re.search(r"\b" + re.escape(term.lower()) + r"\b", title_and_dept):
                matched_term = term
                break

        if matched_term:
            discarded_summary.append(
                f"- **{j_title}** (ID: {j_id}) — *Descartado por término prohibido: '{matched_term}'*"
            )
            continue

        # 2. Check location filters
        loc_passed, loc_reason = filter_job_by_location(job)
        if not loc_passed:
            discarded_summary.append(
                f"- **{j_title}** (ID: {j_id}) — *{loc_reason}*"
            )
            continue

        retained_job_dicts.append(job)

    # Update in-memory cache with retained jobs and stats
    from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache

    set_last_fetched_jobs_cache(
        retained_job_dicts,
        total_raw=len(jobs),
        pre_discarded_summary=discarded_summary,
    )

    # Format response markdown
    now_str = datetime.now().strftime("%d/%m/%Y a las %H:%M hs")
    res_lines = [
        f"🔍 **Tablero Ashby de {board_name.capitalize()}** (Actualizado al {now_str}):\n",
        f"📊 **Resumen del Pre-Filtro Duro (Etapa 2 - 0 Tokens)**:",
        f"- **Total de ofertas detectadas en la API**: {len(jobs)}",
        f"- **Ofertas pre-descartadas automáticamente**: {len(discarded_summary)}",
        f"- **Ofertas conservadas para evaluación**: {len(retained_job_dicts)}\n",
    ]

    if discarded_summary:
        res_lines.append("🚫 **Detalle de ofertas descartadas en Pre-Filtro**:")
        res_lines.extend(discarded_summary[:10])
        if len(discarded_summary) > 10:
            res_lines.append(f"- *...y {len(discarded_summary) - 10} ofertas más descartadas.*")
        res_lines.append("")

    if not retained_job_dicts:
        res_lines.append("⚠️ *No se encontraron vacantes técnicas que superen el pre-filtro de ubicación y perfil.*")
        return "\n".join(res_lines)

    res_lines.append("📋 **Vacantes Técnicas Conservadas**:")
    for idx, j in enumerate(retained_job_dicts, 1):
        j_id = j.get("id")
        j_title = j.get("title")
        j_loc = j.get("location")
        j_mode = j.get("work_mode")
        j_dept = j.get("department")
        res_lines.append(f"{idx}. **{j_title}** [{j_mode} | {j_loc} | {j_dept}] (ID: `{j_id}`)")

    res_lines.append(
        f"\n💡 *Para rankear estas vacantes, indicá qué números deseas evaluar (ej: 'todas', '1, 2' o 'del 1 al {len(retained_job_dicts)}').*"
    )
    return "\n".join(res_lines)
