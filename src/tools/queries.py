"""
Job querying and inspection tools for JobBud.
"""

import json
import re
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
JOBS_FILE_PATH = ROOT_DIR / "jobs.json"


def check_existing_job(identifier: str) -> str:
    """
    Checks if a job posting is already stored or ranked in jobs.json.

    Args:
        identifier: Job ID (e.g. "exactas_86_26", "linkedin_4445031526"), title, or URL.

    Returns:
        String indicating whether the job exists, its ranking score if ranked, or if not found.
    """
    if not JOBS_FILE_PATH.exists():
        return "NotFound: No jobs.json file found."

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
            if not isinstance(jobs, list):
                return "NotFound: jobs.json is empty."

        clean_id = identifier.strip().lower()

        found = None
        for j in jobs:
            j_id = str(j.get("id", "")).lower()
            j_title = str(j.get("title", "")).lower()
            j_url = str(j.get("source_url", "")).lower()

            if clean_id == j_id or clean_id == j_title or (clean_id in j_url and len(clean_id) > 10):
                found = j
                break

        if not found:
            # Match Exactas format (e.g. 86/26 or 86_26) or numeric job IDs (e.g. 5569916, 4445031526)
            id_match = re.search(r'(\d+[\/\-_]\d+|\b\d{5,}\b)', clean_id)
            if id_match:
                target_num = id_match.group(1).replace('/', '_').replace('-', '_')
                for j in jobs:
                    j_id_lower = str(j.get("id", "")).lower()
                    j_url_lower = str(j.get("source_url", "")).lower()
                    if target_num in j_id_lower or target_num in j_url_lower:
                        found = j
                        break


        if found:
            status = found.get("status", "unknown")
            job_title = found.get("title", "Desconocida")
            job_id = found.get("id", "Desconocido")
            score = found.get("score")

            if status == "ranked" and score is not None:
                return (
                    f"AlreadyRanked: Posición con ID '{job_id}' y nombre '{job_title}' "
                    f"ya está almacenada con un puntaje de {score}/100."
                )
            else:
                return (
                    f"AlreadySaved: Posición con ID '{job_id}' y nombre '{job_title}' "
                    f"ya está almacenada en jobs.json (estado: {status}, aún sin puntaje)."
                )

        return f"NotFound: No position found in jobs.json matching identifier '{identifier}'."

    except Exception as e:
        return f"Error checking jobs.json: {str(e)}"


def get_job_raw_text(identifier: str) -> str:
    """
    Retrieves the complete raw original text of a stored job posting from jobs.json.

    Args:
        identifier: Job ID (e.g. "exactas_86_26", "linkedin_4445031526"), title, or URL.

    Returns:
        The raw unparsed text content of the requested job posting.
    """
    if not JOBS_FILE_PATH.exists():
        return "Error: No jobs.json file found."

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        if not isinstance(jobs, list) or not jobs:
            return "Error: No jobs found in jobs.json."

        clean_id = identifier.strip().lower()
        found = None
        for j in jobs:
            j_id = str(j.get("id", "")).lower()
            j_title = str(j.get("title", "")).lower()
            j_url = str(j.get("source_url", "")).lower()

            if clean_id == j_id or clean_id == j_title or (clean_id in j_url and len(clean_id) > 10):
                found = j
                break

        if not found:
            id_match = re.search(r'(\d+[\/\-_]\d+|\b\d{5,}\b)', clean_id)
            if id_match:
                target_num = id_match.group(1).replace('/', '_').replace('-', '_')
                for j in jobs:
                    j_id_lower = str(j.get("id", "")).lower()
                    j_url_lower = str(j.get("source_url", "")).lower()
                    if target_num in j_id_lower or target_num in j_url_lower:
                        found = j
                        break


        if not found:
            return f"Error: No position found matching '{identifier}' in jobs.json."

        job_id = found.get("id", "N/A")
        title = found.get("title", "N/A")
        company = found.get("company", "N/A")
        raw_text = found.get("raw_text") or found.get("summary") or "Sin texto crudo disponible."

        return (
            f"📄 **Texto Original / Postulación Entera**\n"
            f"**ID:** `{job_id}` | **Puesto:** {title} en **{company}**\n\n"
            f"```text\n{raw_text}\n```"
        )

    except Exception as e:
        return f"Error retrieving raw text: {str(e)}"


def get_job_details(identifier: str) -> str:

    """
    Retrieves complete structured details of a job position from jobs.json, including fit score, strengths, gaps, source URL, and exact application instructions.

    Args:
        identifier: Job ID (e.g. "exactas_86_26", "linkedin_4445031526", "greenhouse_invgate_4456847002"), title, or URL.

    Returns:
        Formatted markdown report containing all position fields, fit evaluation, and application link.
    """
    if not JOBS_FILE_PATH.exists():
        return "Error: No jobs.json file found."

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        if not isinstance(jobs, list) or not jobs:
            return "Error: No jobs found in jobs.json."

        clean_id = identifier.strip().lower()
        found = None
        for j in jobs:
            j_id = str(j.get("id", "")).lower()
            j_title = str(j.get("title", "")).lower()
            j_url = str(j.get("source_url", "")).lower()

            if clean_id == j_id or clean_id == j_title or (clean_id in j_url and len(clean_id) > 10):
                found = j
                break

        if not found:
            id_match = re.search(r'(\d+[\/\-_]\d+|\b\d{5,}\b)', clean_id)
            if id_match:
                target_num = id_match.group(1).replace('/', '_').replace('-', '_')
                for j in jobs:
                    j_id_lower = str(j.get("id", "")).lower()
                    j_url_lower = str(j.get("source_url", "")).lower()
                    if target_num in j_id_lower or target_num in j_url_lower:
                        found = j
                        break

        if not found:
            return f"Error: No position found matching '{identifier}' in jobs.json."

        app_method = found.get("application_method") or found.get("source_url") or "Link no disponible"
        source_url = found.get("source_url") or "Link no disponible"
        techs = ", ".join(found.get("key_technologies", [])) or "No especificado"
        reqs = "\n  - ".join(found.get("main_requirements", [])) or "No especificados"
        strengths = ", ".join(found.get("strengths", [])) or "Ninguna registrada"
        gaps = ", ".join(found.get("gaps", [])) or "Ninguno registrado"

        return (
            f"📋 **DETALLES COMPLETOS Y MÉTODO DE POSTULACIÓN DE LA VACANTE**\n\n"
            f"📌 **Puesto, Empresa e ID:**\n"
            f"- **Título:** {found.get('title')}\n"
            f"- **Empresa:** {found.get('company')}\n"
            f"- **ID Único:** `{found.get('id')}`\n"
            f"- **Estado:** `{found.get('status')}`\n\n"
            f"📍 **Ubicación y Modalidad:**\n"
            f"- **Ubicación:** {found.get('location')}\n"
            f"- **Modalidad:** `{found.get('work_mode')}` | **Jornada:** `{found.get('commitment')}`\n\n"
            f"💼 **Seniority y Salario:**\n"
            f"- **Seniority:** `{found.get('seniority')}` | **Salario:** {found.get('salary_range')}\n\n"
            f"💻 **Stack Tecnológico Clave:**\n"
            f"- {techs}\n\n"
            f"📋 **Requisitos Principales:**\n"
            f"  - {reqs}\n\n"
            f"📝 **Resumen del Puesto:**\n"
            f"{found.get('summary')}\n\n"
            f"⭐ **Compatibilidad (Fit Score):** {found.get('score', 'N/A')}/100\n"
            f"- **Justificación:** {found.get('justification')}\n"
            f"- **Fortalezas:** {strengths}\n"
            f"- **Vacíos / Gaps:** {gaps}\n\n"
            f"📩 **CÓMO POSTULARSE Y ENLACE DIRECTO:**\n"
            f"- 🌐 **Link Directo a la Oferta:** [{source_url}]({source_url})\n"
            f"- 📝 **Método / Instrucciones:** {app_method}\n"
        )

    except Exception as e:
        return f"Error retrieving job details: {str(e)}"



def get_top_job_recommendations(top_n: int = 5, include_all_statuses: bool = False) -> str:
    """
    Retrieves the top N best ranked job positions for application, ordered by score descending.

    Args:
        top_n: Number of top recommendations to return (default 5).
        include_all_statuses: If False (default), excludes jobs marked as 'applied' or 'disqualified'.

    Returns:
        Formatted string listing the top N job positions with ID, title, company, summary, score, and recommendation.
    """
    if not JOBS_FILE_PATH.exists():
        return "No hay vacantes registradas en jobs.json."

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        if not isinstance(jobs, list) or not jobs:
            return "No hay vacantes registradas en jobs.json."

        ranked_jobs = []
        for j in jobs:
            score = j.get("score")
            status = j.get("status", "")
            if score is not None:
                if not include_all_statuses and status in ("applied", "disqualified"):
                    continue
                ranked_jobs.append(j)

        if not ranked_jobs:
            return "No se encontraron posiciones evaluadas disponibles para postularse (que no estén aplicadas o descalificadas)."

        ranked_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_candidates = ranked_jobs[:top_n]

        output = f"🏆 Top {len(top_candidates)} mejores ofertas para postularse:\n\n"
        for i, j in enumerate(top_candidates, 1):
            j_id = j.get("id", "N/A")
            title = j.get("title", "N/A")
            company = j.get("company", "N/A")
            score = j.get("score", 0)
            summary = j.get("summary", "Sin descripción disponible.")
            work_mode = j.get("work_mode", "N/A")
            location = j.get("location", "N/A")

            output += (
                f"### {i}. [{j_id}] {title} en **{company}**\n"
                f"- **⭐ Puntaje:** `{score}/100`\n"
                f"- **📍 Ubicación/Modalidad:** {location} ({work_mode})\n"
                f"- **📝 Descripción:** {summary}\n\n"
            )

        return output

    except Exception as e:
        return f"Error retrieving top job recommendations: {str(e)}"


def list_jobs_by_status(status_filter: Optional[str] = None) -> str:
    """
    Lists stored jobs filtered by status ('applied', 'disqualified', 'ranked', 'pending_ranking') or all jobs.

    Args:
        status_filter: Optional filter ('applied'/'aplicadas', 'disqualified'/'descartadas', 'ranked', etc.).

    Returns:
        Formatted summary of matching job positions.
    """
    if not JOBS_FILE_PATH.exists():
        return "No hay vacantes registradas en jobs.json."

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        if not jobs:
            return "No hay vacantes registradas en jobs.json."

        status_map = {
            "disqualified": "disqualified",
            "descartadas": "disqualified",
            "descalificadas": "disqualified",
            "applied": "applied",
            "aplicadas": "applied",
            "postuladas": "applied",
            "ranked": "ranked",
            "pending_ranking": "pending_ranking"
        }

        target_status = status_map.get(status_filter.strip().lower(), status_filter.strip().lower()) if status_filter else None

        matching = [j for j in jobs if (target_status is None or j.get("status") == target_status)]

        if not matching:
            filter_text = f" con estado '{target_status}'" if target_status else ""
            return f"No se encontraron posiciones{filter_text} en jobs.json."

        out = f"Se encontraron {len(matching)} posición(es) en jobs.json:\n\n"
        for j in matching:
            score_str = f" (Score: {j['score']}/100)" if j.get("score") is not None else ""
            notes_str = f" | Notas: {j['user_notes']}" if j.get("user_notes") else ""
            out += f"- **[{j.get('id', 'N/A')}]** {j.get('title', 'N/A')} en *{j.get('company', 'N/A')}* — Estado: `{j.get('status', 'unknown')}`{score_str}{notes_str}\n"

        return out

    except Exception as e:
        return f"Error listing jobs: {str(e)}"


TITLE_BLACKLIST_PATH = ROOT_DIR / "profile" / "title_blacklist.md"
DEPARTMENT_BLACKLIST_PATH = ROOT_DIR / "profile" / "department_blacklist.md"
BLACKLIST_ROLES_PATH = ROOT_DIR / "profile" / "blacklist_roles.md"
BLACKLIST_SENIORITY_PATH = ROOT_DIR / "profile" / "blacklist_seniority.md"


def _read_md_list_file(filepath: Path) -> list[str]:
    if not filepath.exists():
        return []
    terms = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(("-", "*")):
                    term = line.lstrip("-* ").strip()
                    if term:
                        terms.append(term)
    except Exception:
        pass
    return terms


def load_title_blacklist() -> list[str]:
    """Reads hard title blacklist terms from profile/title_blacklist.md."""
    return _read_md_list_file(TITLE_BLACKLIST_PATH)


def load_department_blacklist() -> list[str]:
    """Reads hard department blacklist terms from profile/department_blacklist.md."""
    return _read_md_list_file(DEPARTMENT_BLACKLIST_PATH)


def load_blacklist_roles() -> list[str]:
    """Reads role/area blacklist terms from profile/blacklist_roles.md."""
    return _read_md_list_file(BLACKLIST_ROLES_PATH)


def load_blacklist_seniority() -> list[str]:
    """Reads seniority level blacklist terms from profile/blacklist_seniority.md."""
    return _read_md_list_file(BLACKLIST_SENIORITY_PATH)


def load_blacklist_terms() -> list[str]:
    """Reads all excluded terms combined from title, department, role, and seniority blacklists."""
    titles = load_title_blacklist()
    departments = load_department_blacklist()
    roles = load_blacklist_roles()
    seniority = load_blacklist_seniority()
    return list(dict.fromkeys(titles + departments + roles + seniority))




def filter_jobs_by_blacklist(jobs_text: str) -> str:
    """
    Filters job posting text by excluding positions whose TITLE contains any blacklisted term defined in profile/blacklist_roles.md or profile/blacklist_seniority.md.

    Args:
        jobs_text: The raw or formatted text of one or more job postings.

    Returns:
        Filtered job text with blacklisted positions omitted and a summary of excluded jobs.
    """
    terms = load_blacklist_terms()
    if not terms or not jobs_text.strip():
        return jobs_text

    # Split offers format: "--- OFERTA "
    if "--- OFERTA " in jobs_text:
        parts = jobs_text.split("--- OFERTA ")
        header = parts[0]
        retained = []
        discarded_summary = []

        for part in parts[1:]:
            full_offer = "--- OFERTA " + part
            title_match = re.search(r"Title:\s*(.*)", part, re.IGNORECASE)
            title_text = title_match.group(1).strip() if title_match else part.strip().splitlines()[0]
            title_lower = title_text.lower()

            matched_term = None
            for term in terms:
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, title_lower):
                    matched_term = term
                    break

            if matched_term:
                discarded_summary.append(f"- {title_text} (Título filtrado por: '{matched_term}')")
            else:
                retained.append(full_offer)

        summary_msg = ""
        if discarded_summary:
            summary_msg = f"\n\n🚫 **Ofertas omitidas por título en blacklists de roles/seniority ({len(discarded_summary)}):**\n" + "\n".join(discarded_summary[:10])
            if len(discarded_summary) > 10:
                summary_msg += f"\n... y {len(discarded_summary) - 10} oferta(s) más."

        return header.strip() + "\n\n" + "\n\n".join(retained) + summary_msg

    elif "Oferta #" in jobs_text:
        offers = re.split(r'(?=Oferta\s*#)', jobs_text)
        retained = []
        discarded_summary = []

        for off in offers:
            if not off.strip():
                continue
            title_match = re.search(r"Nombre del puesto:\s*([^\n\r/]+)", off, re.IGNORECASE)
            title_text = title_match.group(1).strip() if title_match else off.strip().splitlines()[0]
            title_lower = title_text.lower()

            matched_term = None
            for term in terms:
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, title_lower):
                    matched_term = term
                    break

            if matched_term:
                discarded_summary.append(f"- {title_text} (Título filtrado por: '{matched_term}')")
            else:
                retained.append(off.strip())

        summary_msg = ""
        if discarded_summary:
            summary_msg = f"\n\n🚫 **Ofertas omitidas por título en blacklists de roles/seniority ({len(discarded_summary)}):**\n" + "\n".join(discarded_summary[:10])
            if len(discarded_summary) > 10:
                summary_msg += f"\n... y {len(discarded_summary) - 10} oferta(s) más."

        return "\n\n".join(retained) + summary_msg

    else:
        # Single job post check
        title_match = re.search(r"Title:\s*(.*)", jobs_text, re.IGNORECASE) or re.search(r"Nombre del puesto:\s*([^\n\r/]+)", jobs_text, re.IGNORECASE)
        title_text = title_match.group(1).strip() if title_match else jobs_text.strip().splitlines()[0]
        title_lower = title_text.lower()

        for term in terms:
            pattern = r"\b" + re.escape(term.lower()) + r"\b"
            if re.search(pattern, title_lower):
                return (
                    f"⚠️ **Oferta omitida por blacklists de roles/seniority** (Título '{title_text}' contiene: '{term}').\n"
                    f"Se ignora la evaluación visual de esta posición."
                )
        return jobs_text


LOCATION_FILTERS_PATH = ROOT_DIR / "profile" / "location_filters.json"


def load_location_filters() -> dict:
    """Reads structured location and work mode filter configuration from profile/location_filters.json."""
    if not LOCATION_FILTERS_PATH.exists():
        return {
            "work_modes": {
                "allow_remote": True,
                "allow_hybrid": True,
                "allow_onsite": True,
                "allow_unspecified": True
            },
            "location_preferences": {
                "allow_unspecified_location": True,
                "allowed_remote_regions": [],
                "allowed_onsite_or_hybrid_cities": [],
                "blocked_countries_or_cities": []
            }
        }
    try:
        with open(LOCATION_FILTERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def filter_job_by_location(job: dict) -> tuple[bool, str]:
    """
    Evaluates a structured job dict against deterministic location and work_mode rules in profile/location_filters.json.

    Args:
        job: Dictionary representing a job position (must contain 'location' and 'work_mode').

    Returns:
        Tuple (passed: bool, reason: str)
    """
    filters = load_location_filters()
    work_config = filters.get("work_modes", {})
    loc_config = filters.get("location_preferences", {})

    location = str(job.get("location", "")).strip()
    work_mode = str(job.get("work_mode", "")).strip()
    location_lower = location.lower()
    work_mode_lower = work_mode.lower()

    # 1. Check blocked countries
    blocked_list = loc_config.get("blocked_countries", []) + loc_config.get("blocked_countries_or_cities", [])
    for blocked in blocked_list:
        if blocked and re.search(r"\b" + re.escape(blocked.lower()) + r"\b", location_lower):
            return False, f"País bloqueado explícitamente por profile/location_filters.json: '{location}'"

    # 2. Check unspecified work mode
    is_unspecified_work_mode = work_mode_lower in ("not specified", "desconocida", "no especificada", "", "n/a")
    if is_unspecified_work_mode:
        if not work_config.get("allow_unspecified", True):
            return False, "Modalidad no especificada (desactivada en profile/location_filters.json)"

    # 3. Check unspecified location
    is_unspecified_location = location_lower in ("not specified", "desconocida", "no especificada", "no aclarada", "unspecified", "none", "null", "", "n/a")
    if is_unspecified_location:
        if not loc_config.get("allow_unspecified_location", True):
            return False, "Ubicación / país no especificado (desactivado en profile/location_filters.json)"
        else:
            return True, "Ubicación / país no especificado (permitido según profile/location_filters.json)"


    # 4. Specific Work Mode checks
    if "remote" in work_mode_lower or "remoto" in work_mode_lower:
        if not work_config.get("allow_remote", True):
            return False, "Modalidad Remota desactivada en profile/location_filters.json"
    elif "hybrid" in work_mode_lower or "híbrido" in work_mode_lower or "hibrido" in work_mode_lower:
        if not work_config.get("allow_hybrid", True):
            return False, "Modalidad Híbrida desactivada en profile/location_filters.json"
    elif "on-site" in work_mode_lower or "presencial" in work_mode_lower or "onsite" in work_mode_lower:
        if not work_config.get("allow_onsite", True):
            return False, "Modalidad Presencial desactivada en profile/location_filters.json"

    # 5. Strict Country, City, and Remote Region matching
    if not is_unspecified_location:
        allowed_countries = loc_config.get("allowed_countries", [])
        allowed_cities = loc_config.get("allowed_cities", [])
        allowed_regions = loc_config.get("allowed_remote_regions", [])

        is_remote_job = "remote" in work_mode_lower or "remoto" in work_mode_lower or "remote" in location_lower or "remoto" in location_lower

        matched_country = any(re.search(r"\b" + re.escape(c.lower()) + r"\b", location_lower) for c in allowed_countries if c)
        matched_city = any(re.search(r"\b" + re.escape(city.lower()) + r"\b", location_lower) for city in allowed_cities if city)
        matched_region = any(re.search(r"\b" + re.escape(r.lower()) + r"\b", location_lower) for r in allowed_regions if r)

        if is_remote_job:
            # Remote jobs ONLY check allowed_remote_regions and allowed_countries
            if allowed_regions and not (matched_region or matched_country or "worldwide" in location_lower or "anywhere" in location_lower or "global" in location_lower):
                return False, f"Ubicación Remota '{location}' fuera de las regiones permitidas en profile/location_filters.json"
        else:
            # On-site or Hybrid jobs check allowed_countries OR allowed_cities OR allowed_regions
            if (allowed_countries or allowed_cities) and not (matched_country or matched_city or matched_region):
                return False, f"Ubicación Presencial/Híbrida '{location}' fuera de las ciudades/países permitidos en profile/location_filters.json"

    return True, "País, ciudad y modalidad permitidos según profile/location_filters.json"


def evaluate_post_parse_filters(job: dict) -> tuple[bool, str]:
    """
    Evaluates a parsed job dict against post-parse filters (blacklist_roles.md, blacklist_seniority.md, and location_filters.json).

    Args:
        job: Parsed job dictionary.

    Returns:
        Tuple (passed: bool, reason: str)
    """
    title = str(job.get("title", "")).lower()
    department = str(job.get("department", "")).lower()
    seniority = str(job.get("seniority", "")).lower()

    # 1. Check Role Blacklist against title and department
    roles = load_blacklist_roles()
    for role in roles:
        pattern = r"\b" + re.escape(role.lower()) + r"\b"
        if re.search(pattern, title) or (department and re.search(pattern, department)):
            return False, f"Rol/Área '{role}' descartado por profile/blacklist_roles.md"

    # 2. Check Seniority Blacklist against title and seniority
    seniorities = load_blacklist_seniority()
    for sen in seniorities:
        pattern = r"\b" + re.escape(sen.lower()) + r"\b"
        if re.search(pattern, title) or (seniority and re.search(pattern, seniority)):
            return False, f"Seniority '{sen}' descartado por profile/blacklist_seniority.md"

    # 3. Check Location & Work Mode Filters
    loc_passed, loc_reason = filter_job_by_location(job)
    if not loc_passed:
        return False, loc_reason

    # 4. Check Years of Experience Filter
    from src.subagents.job_pipeline.runner import load_pipeline_config
    cfg = load_pipeline_config()
    max_years = cfg.get("max_years_experience", 3)

    raw_yexp = job.get("years_of_experience")
    if raw_yexp and str(raw_yexp).lower() not in ("undefined", "none", "null", ""):
        try:
            num_y = int(str(raw_yexp).split("-")[0].strip())
            if num_y > max_years:
                return False, f"Años de experiencia requeridos ({num_y}) superan el máximo configurado ({max_years} años)"
        except Exception:
            pass

    return True, "Apto según filtros de rol, seniority, experiencia y ubicación"
