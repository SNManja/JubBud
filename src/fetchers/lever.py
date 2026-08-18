"""
Lever Public Postings API fetcher for JobBud.
Fetches single job postings or full job boards via official Lever Public Postings API.
Returns normalized List[JobDict] (0 LLM tokens spent) and provides the agent tool.
"""

import html
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from src.fetchers.base import compress_job_text, extract_technologies_from_text
from src.subagents.job_parser.tools import build_unified_job_dict


def parse_lever_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts (company_slug, job_id) from a Lever URL or API endpoint.

    Args:
        url: Lever job post or job board URL.

    Returns:
        Tuple of (company_slug, job_id). job_id is None for board-level URLs.
    """
    cleaned_url = url.strip()

    # 1. Direct API endpoint match: e.g. api.lever.co/v0/postings/despegar or /postings/despegar/62feca6a-...
    api_match = re.search(
        r"api\.lever\.co/v0/postings/([a-zA-Z0-9_\-]+)(?:/([a-zA-Z0-9_\-]+))?",
        cleaned_url,
        re.IGNORECASE,
    )
    if api_match:
        return api_match.group(1), api_match.group(2)

    # 2. Hosted Lever URL with job ID: e.g. jobs.lever.co/resilientco/62feca6a-8049-453d-b796-5ffbfbe8cccc(/apply)?
    job_match = re.search(
        r"lever\.co/([a-zA-Z0-9_\-]+)/([a-f0-9\-]{36}|[a-zA-Z0-9_\-]+)(?:/.*)?",
        cleaned_url,
        re.IGNORECASE,
    )
    if job_match:
        comp = job_match.group(1)
        jid = job_match.group(2)
        if comp.lower() not in ("v0", "postings", "embed", "api"):
            if jid.lower() not in ("apply", "thanks"):
                return comp, jid
            return comp, None

    # 3. Hosted Lever board URL: e.g. jobs.lever.co/company or jobs.lever.co/company/
    board_match = re.search(
        r"lever\.co/([a-zA-Z0-9_\-]+)",
        cleaned_url,
        re.IGNORECASE,
    )
    if board_match:
        comp = board_match.group(1)
        if comp.lower() not in ("v0", "postings", "embed", "api"):
            return comp, None

    return None, None


def _detect_language_deterministic(text: str) -> str:
    """
    Simple deterministic language detection based on frequency of common Spanish vs English stop words.
    0 LLM tokens spent.
    """
    sample = (text or "")[:1500].lower()
    spanish_markers = len(
        re.findall(
            r"\b(de|en|para|con|por|requisitos|experiencia|trabajo|puesto|conocimientos|modalidad|remoto|híbrido|estudiante|carrera|años)\b",
            sample,
        )
    )
    english_markers = len(
        re.findall(
            r"\b(the|and|in|with|for|requirements|experience|skills|role|responsibilities|job|work|years|team|company)\b",
            sample,
        )
    )

    if spanish_markers > english_markers and spanish_markers >= 3:
        return "es"
    return "en"


def _normalize_work_mode(workplace_type: Optional[str], commitment_str: Optional[str]) -> str:
    """Normalizes Lever workplace type and commitment to JobBud standard."""
    wt_clean = str(workplace_type or "").strip().lower()
    comm_clean = str(commitment_str or "").strip().lower()

    if wt_clean == "remote" or "remote" in comm_clean:
        return "Remote"
    elif wt_clean in ("hybrid", "híbrido", "hibrido") or "hybrid" in comm_clean or "híbrido" in comm_clean:
        return "Hybrid"
    elif wt_clean in ("onsite", "on-site", "on_site") or "on-site" in comm_clean or "onsite" in comm_clean:
        return "On-site"
    return "Not specified"


def _normalize_commitment(commitment_raw: Optional[str], title: str = "") -> str:
    """Normalizes Lever commitment to JobBud standard."""
    c_lower = str(commitment_raw or "").lower().strip()
    title_lower = title.lower()

    if "intern" in c_lower or "pasant" in c_lower or "intern" in title_lower or "pasant" in title_lower:
        return "Internship"
    if "part-time" in c_lower or "part time" in c_lower or "medio tiempo" in c_lower:
        return "Part-time"
    if "contract" in c_lower or "contractor" in c_lower or "freelance" in c_lower:
        return "Contract"
    if "full-time" in c_lower or "full time" in c_lower or "tiempo completo" in c_lower:
        return "Full-time"
    if "temporary" in c_lower or "temporal" in c_lower:
        return "Temporary"
    return "Full-time" if "full" in c_lower else "Not specified"


def _clean_lever_description(item: Dict[str, Any]) -> str:
    """
    Extracts, formats, and compresses full job description text from Lever posting object.
    Combines descriptionPlain, structured HTML lists, and additionalPlain.
    """
    parts = []

    # 1. Opening / Description
    desc_plain = (item.get("descriptionPlain") or "").strip()
    if not desc_plain and item.get("description"):
        soup = BeautifulSoup(html.unescape(item.get("description")), "html.parser")
        desc_plain = soup.get_text("\n", strip=True)
    if desc_plain:
        parts.append(desc_plain)

    # 2. Structured Lists (Responsibilities, Requirements, Must-Have, etc.)
    for l in item.get("lists", []):
        if not isinstance(l, dict):
            continue
        header = (l.get("text") or "").strip()
        content_html = l.get("content", "")
        if content_html:
            soup = BeautifulSoup(html.unescape(content_html), "html.parser")
            bullets = [
                li.get_text(" ", strip=True)
                for li in soup.find_all("li")
                if li.get_text(strip=True)
            ]
            if bullets:
                list_text = "\n".join(f"- {b}" for b in bullets)
                parts.append(f"{header}\n{list_text}" if header else list_text)
            else:
                raw_l = soup.get_text("\n", strip=True)
                if raw_l:
                    parts.append(f"{header}\n{raw_l}" if header else raw_l)

    # 3. Additional notes / Perks / Culture
    add_plain = (item.get("additionalPlain") or "").strip()
    if not add_plain and item.get("additional"):
        soup = BeautifulSoup(html.unescape(item.get("additional")), "html.parser")
        add_plain = soup.get_text("\n", strip=True)
    if add_plain:
        parts.append(add_plain)

    full_text = "\n\n".join(parts)
    return compress_job_text(full_text)


def fetch_lever_jobs(url: str) -> List[Dict[str, Any]]:
    """
    Fetches job details or full board listings from Lever using the official Public Postings API.

    Args:
        url: Lever job posting URL or job board URL.

    Returns:
        List of normalized JobDict objects (single element if specific job ID, multiple if board).
    """
    cleaned_url = url.strip()
    company_slug, target_job_id = parse_lever_url(cleaned_url)

    if not company_slug:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    # Case A: Specific single job ID requested
    if target_job_id:
        api_url = f"https://api.lever.co/v0/postings/{company_slug}/{target_job_id}?mode=json"
        try:
            resp = requests.get(api_url, headers=headers, timeout=12)
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw_jobs = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
        except Exception:
            return []
    else:
        # Case B: Full board listing
        api_url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
        try:
            resp = requests.get(api_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw_jobs = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
        except Exception:
            return []

    if not raw_jobs:
        return []

    normalized_jobs: List[Dict[str, Any]] = []

    for item in raw_jobs:
        if not isinstance(item, dict):
            continue

        job_id_raw = str(item.get("id") or "").strip()
        hosted_url = item.get("hostedUrl", "")
        apply_url = item.get("applyUrl", "")

        # Target job filtering if needed
        if target_job_id and job_id_raw.lower() != target_job_id.lower():
            continue

        title = str(item.get("text") or "Untitled").strip()

        # Parse and format created timestamp
        created_at_ms = item.get("createdAt")
        if created_at_ms and isinstance(created_at_ms, (int, float)):
            try:
                dt = datetime.fromtimestamp(created_at_ms / 1000.0, timezone.utc)
                created_at = dt.isoformat()
            except Exception:
                created_at = datetime.now().isoformat()
        else:
            created_at = datetime.now().isoformat()

        # Categories: location, department, team, commitment
        cats = item.get("categories") or {}
        if not isinstance(cats, dict):
            cats = {}

        primary_loc = cats.get("location")
        all_locs_raw = cats.get("allLocations") or []
        if not isinstance(all_locs_raw, list):
            all_locs_raw = [all_locs_raw] if all_locs_raw else []

        loc_list = []
        if primary_loc:
            loc_list.append(str(primary_loc).strip())
        for l in all_locs_raw:
            l_str = str(l).strip()
            if l_str and l_str not in loc_list:
                loc_list.append(l_str)

        country_code = item.get("country")
        location = "; ".join(loc_list) if loc_list else (str(country_code) if country_code else "Not specified")

        # Department & Team
        dept = cats.get("department")
        team = cats.get("team")
        if dept and team and str(dept).strip().lower() != str(team).strip().lower():
            full_dept = f"{str(dept).strip()} - {str(team).strip()}"
        else:
            full_dept = str(dept or team or "Not specified").strip()

        # Work Mode & Commitment
        work_mode = _normalize_work_mode(item.get("workplaceType"), cats.get("commitment"))
        commitment = _normalize_commitment(cats.get("commitment"), title)

        # Description and compressed raw text
        clean_desc = _clean_lever_description(item)
        if not clean_desc:
            clean_desc = title

        # Compensation / Salary Range
        salary_obj = item.get("salaryRange")
        salary_range = "Not specified"
        if isinstance(salary_obj, dict):
            s_min = salary_obj.get("min")
            s_max = salary_obj.get("max")
            s_curr = salary_obj.get("currency", "")
            s_interval = salary_obj.get("interval", "")
            if s_min is not None and s_max is not None and (s_min > 0 or s_max > 0):
                interval_str = f" ({s_interval})" if s_interval else ""
                salary_range = f"{s_curr} {s_min:,} - {s_max:,}{interval_str}".strip()

        # Technologies & Language
        found_techs = extract_technologies_from_text(f"{title}\n{clean_desc}")
        lang = _detect_language_deterministic(f"{title}\n{clean_desc}")

        # Canonical ID and Application Method
        stable_id = f"lever_{company_slug.lower()}_{job_id_raw.lower()}" if job_id_raw else f"lever_{company_slug.lower()}"
        source_url = hosted_url or cleaned_url
        app_method = f"Postulación web en: {apply_url or hosted_url or source_url}"

        summary_paras = [p.strip() for p in clean_desc.split("\n\n") if len(p.strip()) > 30]
        summary = summary_paras[0] if summary_paras else clean_desc[:200]

        job_dict = build_unified_job_dict(
            title=title,
            company=company_slug,
            location=location,
            work_mode=work_mode,
            commitment=commitment,
            department=full_dept,
            salary_range=salary_range,
            key_technologies=found_techs,
            main_requirements=[],
            summary=summary[:300],
            raw_text=clean_desc,
            language=lang,
            source_page=f"Lever ({company_slug})",
            source_url=source_url,
            job_id=stable_id,
            application_method=app_method,
            status="new",
        )
        # Preserve original created_at timestamp
        job_dict["created_at"] = created_at

        normalized_jobs.append(job_dict)

        if target_job_id and len(normalized_jobs) == 1:
            break

    return normalized_jobs


def fetch_lever_job_content(url: str) -> str:
    """
    Agent tool: Fetches job descriptions or board listings from Lever Public Postings API,
    applies hard pre-filters (Stage 2), and sets the in-memory candidate cache.

    Args:
        url: Lever job posting URL or job board URL.

    Returns:
        Formatted text summary and candidates listing for user interaction.
    """
    cleaned_url = url.strip()
    company_slug, job_id = parse_lever_url(cleaned_url)

    if not company_slug:
        return (
            "Error: Could not extract a valid Lever company slug or job ID from the provided URL. "
            "Please check the URL or paste the job description text directly."
        )

    jobs = fetch_lever_jobs(cleaned_url)
    if not jobs:
        if job_id:
            return f"Error: Job ID '{job_id}' was not found on Lever board '{company_slug}' or could not be retrieved."
        return f"No active job postings found on Lever board '{company_slug}'."

    # Single job posting view
    if job_id and len(jobs) == 1:
        job = jobs[0]
        from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache

        set_last_fetched_jobs_cache(jobs, total_raw=1, pre_discarded_summary=[])
        return (
            f"Source Page: Lever ({company_slug})\n"
            f"Source URL: {job.get('source_url', cleaned_url)}\n"
            f"Lever Job ID: {job_id}\n"
            f"Company: {company_slug}\n"
            f"Title: {job.get('title')}\n"
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
        j_id = job.get("id", "lever_job")
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
        f"🔍 **Tablero Lever de {company_slug.capitalize()}** (Actualizado al {now_str}):\n",
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
        j_comm = j.get("commitment")
        j_dept = j.get("department")

        info_parts = [f"Modalidad: {j_mode}"]
        if j_comm and j_comm != "Not specified":
            info_parts.append(f"Dedicación: {j_comm}")
        if j_dept and j_dept != "Not specified":
            info_parts.append(f"Área: {j_dept}")
        if j_loc and j_loc != "Not specified":
            info_parts.append(f"Ubicación: {j_loc}")

        res_lines.append(f"{idx}. **{j_title}** (`{j_id}`)")
        res_lines.append(f"   - {', '.join(info_parts)}")

    res_lines.append(
        f"\n💡 *Para analizar estas vacantes, puedes indicar los números (ej. '1, 2' o 'todas') para ejecutar el pipeline de rankeo.*"
    )

    return "\n".join(res_lines)
