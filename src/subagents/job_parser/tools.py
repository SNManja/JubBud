"""
Tools specific to the JobParser subagent.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any

ROOT_DIR = Path(__file__).resolve().parents[3]
JOBS_FILE_PATH = ROOT_DIR / "jobs.json"


def _generate_stable_job_id(
    title: str = "",
    company: str = "",
    summary: str = "",
    source_page: str = "",
    source_url: Optional[str] = None,
    job_id: Optional[str] = None
) -> str:
    """Generates a stable, deterministic job ID based on source URL and job details."""
    if job_id and str(job_id).strip() and str(job_id).strip().lower() not in ("none", "null", "undefined", ""):
        cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(job_id).strip())
        return cleaned.lower()

    s_url = (source_url or "").strip()
    text_to_search = f"{title} {summary} {s_url}"

    # 1. Greenhouse from URL patterns
    if s_url:
        gh_match = re.search(r'(?:for=([a-zA-Z0-9_\-]+).*token=(\d+))|(?:job-boards\.greenhouse\.io/([a-zA-Z0-9_\-]+)/jobs/(\d+))|(?:greenhouse\.io/(?:embed/)?([a-zA-Z0-9_\-]+)/(?:jobs/)?(\d+))', s_url, re.IGNORECASE)
        if gh_match:
            groups = [g for g in gh_match.groups() if g]
            if len(groups) >= 2:
                return f"greenhouse_{groups[0].lower()}_{groups[1]}"

        # 2. LinkedIn from URL
        li_match = re.search(r'(?:view/|jobid[=_]|currentJobId=)(\d+)', s_url, re.IGNORECASE)
        if li_match:
            return f"linkedin_{li_match.group(1)}"
        if "linkedin" in s_url.lower():
            li_num = re.search(r'(\d{8,11})', s_url)
            if li_num:
                return f"linkedin_{li_num.group(1)}"

        # 3. Exactas UBA from URL or text
        exactas_url_match = re.search(r'(\d+[\/\-_]\d+)', s_url, re.IGNORECASE)
        if exactas_url_match and ("exactas" in s_url.lower() or "exactas" in (source_page or "").lower()):
            num_part = exactas_url_match.group(1).replace('/', '_').replace('-', '_')
            return f"exactas_{num_part}"

        # 4. Ashby from URL
        ashby_match = re.search(r'ashbyhq\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-]+)', s_url, re.IGNORECASE)
        if ashby_match:
            return f"ashby_{ashby_match.group(1).lower()}_{ashby_match.group(2).lower()}"

    # Exactas match in title or summary text
    exactas_match = re.search(r'Oferta\s*#?\s*(\d+[\/\-_]\d+)', text_to_search, re.IGNORECASE)
    if exactas_match:
        num_part = exactas_match.group(1).replace('/', '_').replace('-', '_')
        return f"exactas_{num_part}"

    exactas_match_simple = re.search(r'Oferta\s*#?\s*(\d+)', text_to_search, re.IGNORECASE)
    if source_page and "exactas" in source_page.lower() and exactas_match_simple:
        return f"exactas_{exactas_match_simple.group(1)}"

    # Deterministic hash fallback for manual or un-ID'd postings
    clean_company = company.strip().lower() if company else "unknown"
    clean_title = title.strip().lower() if title else "job"
    raw_key = f"{clean_company}:{clean_title}"
    hash_hex = hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:8]
    prefix = "exactas" if (source_page and "exactas" in source_page.lower()) else ("linkedin" if (source_page and "linkedin" in source_page.lower()) else "manual")
    return f"{prefix}_{hash_hex}"


def _extract_application_method(
    text: str,
    source_url: Optional[str],
    application_method: Optional[str] = None,
    company: str = "",
    job_id: str = ""
) -> str:
    if application_method and str(application_method).strip() and str(application_method).strip().lower() not in ("not specified", "no especificada", "none", "null", "no especificado en el aviso", ""):
        return str(application_method).strip()

    full_text = text or ""

    # 1. Search email contact in raw text
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', full_text)
    ref_match = re.search(r'(?:referencia|ref[:\s]*)(.*)', full_text, re.IGNORECASE)

    if email_match:
        email = email_match.group(0)
        ref_text = f" (Ref: {ref_match.group(1).strip()})" if ref_match else ""
        return f"Enviar CV por correo a {email}{ref_text}"

    # 2. Use explicit source_url
    if source_url and str(source_url).strip() and str(source_url).strip().lower() not in ("none", "null", ""):
        return f"Postulación web en: {str(source_url).strip()}"

    # 3. Search HTTP/HTTPS URL in raw text
    url_in_text = re.search(r'https?://[^\s<>"\'`()]+', full_text)
    if url_in_text:
        clean_url = url_in_text.group(0).rstrip('.,;:')
        return f"Postulación web en: {clean_url}"

    # 4. Construct URL from Greenhouse/LinkedIn/Exactas IDs or company name in registered boards
    clean_jid = str(job_id or "").strip().lower()
    clean_comp = str(company or "").strip().lower()

    if "greenhouse_" in clean_jid:
        parts = clean_jid.split("_")
        if len(parts) >= 3:
            board_tok, j_num = parts[1], parts[2]
            return f"Postulación web en: https://job-boards.greenhouse.io/{board_tok}/jobs/{j_num}"
    elif "linkedin_" in clean_jid:
        parts = clean_jid.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"Postulación web en: https://www.linkedin.com/jobs/view/{parts[1]}"
    elif "exactas_" in clean_jid:
        parts = clean_jid.split("_")
        if len(parts) >= 2:
            num_p = f"{parts[1]}/{parts[2]}" if len(parts) >= 3 else parts[1]
            return f"Postulación web en: https://empleos.exactas.uba.ar/oferta/{num_p}"

    if clean_comp and clean_comp not in ("not specified", "unknown", "none", "null", ""):
        try:
            from src.tools.boards import _load_board_urls
            boards = _load_board_urls()
            for b in boards:
                b_name = str(b.get("name", "")).lower()
                b_id = str(b.get("id", "")).lower()
                if clean_comp in b_name or b_name in clean_comp or clean_comp in b_id:
                    return f"Postulación web en el portal de {b.get('name')}: {b.get('url')}"
        except Exception:
            pass

    return "No especificado en el aviso (ver portal de la empresa)"


def extract_years_of_experience(title: str = "", text: str = "") -> Any:
    """
    Extracts required years of experience from title and raw text.
    Returns int (e.g. 5), range string (e.g. "3-5"), or "undefined" if not inferrable.
    """
    full_text = f"{title or ''}\n{text or ''}"

    # 1. Range pattern: e.g. "3 to 5 years", "3-5 años", "2 - 4 years"
    range_match = re.search(r'(\d+)\s*(?:a|to|-)\s*(\d+)\s*(?:\+|\s)*(?:years?|años?)', full_text, re.IGNORECASE)
    if range_match:
        min_y, max_y = range_match.group(1), range_match.group(2)
        return f"{min_y}-{max_y}"

    # 2. Minimum/Exact pattern: e.g. "minimum 5 years", "5+ years", "5 años de experiencia", "at least 3 years"
    min_match = re.search(r'(?:minimum|mínimo|at least|al menos|experiencia)?\s*\(?\s*(\d+)\+?\s*(?:years?|años?)\b', full_text, re.IGNORECASE)
    if min_match:
        val = int(min_match.group(1))
        if 1 <= val <= 25:
            return val

    return "undefined"


def extract_seniority(title: str, text: str, seniority: Optional[str] = None, years_of_exp: Optional[Any] = None) -> str:
    if seniority and str(seniority).strip() and str(seniority).strip().lower() not in ("not specified", "no especificada", "desconocida", "undefined", ""):
        return str(seniority).strip()

    title_lower = (title or "").lower()
    text_lower = (text or "").lower()

    # 1. Title Seniority Check (highest priority)
    if re.search(r"\b(trainee|pasante|pasantía|internship|intern)\b", title_lower):
        return "Trainee"
    if re.search(r"\b(junior|jr|entry level|entry-level)\b", title_lower):
        return "Junior"
    if re.search(r"\b(semi-senior|semi senior|ssr|semisenior|mid|mid-level|middle)\b", title_lower):
        return "Semi-Senior"
    if re.search(r"\b(senior|sr)\b", title_lower):
        return "Senior"
    if re.search(r"\b(lead|staff|principal|head|manager|director|vp|architect|arquitecto)\b", title_lower):
        return "Lead / Executive"

    # 2. Text Body Seniority Check (fallback if title doesn't specify)
    if re.search(r"\b(trainee|pasante|pasantía|internship)\b", text_lower):
        return "Trainee"
    if re.search(r"\b(junior|jr|estudiante|estudiantes avanzados?)\b", text_lower):
        return "Junior"
    if re.search(r"\b(semi-senior|semi senior|ssr|semisenior|mid|mid-level|middle)\b", text_lower):
        return "Semi-Senior"
    if re.search(r"\b(senior|sr)\b", text_lower):
        return "Senior"
    if re.search(r"\b(lead|staff|principal|architect|arquitecto|head|manager|director|vp)\b", text_lower):
        return "Lead / Executive"

    # 3. Infer from Years of Experience if available
    if years_of_exp and str(years_of_exp).lower() != "undefined":
        try:
            num = int(str(years_of_exp).split("-")[0].strip())
            if num >= 5:
                return "Senior"
            elif num >= 3:
                return "Semi-Senior"
            elif num >= 1:
                return "Junior"
            elif num == 0:
                return "Trainee"
        except Exception:
            pass

    return "undefined"


def extract_commitment(title: str = "", text: str = "", commitment: Optional[str] = None) -> str:
    """
    Extracts employment commitment (Full-time, Part-time, Internship, Not specified)
    using strict word boundaries to avoid false positives from words like 'internal' or 'international'.
    """
    if commitment and str(commitment).strip() and str(commitment).strip().lower() not in ("not specified", "no especificada", "unknown", ""):
        c_clean = str(commitment).strip()
        if c_clean.lower() == "internship":
            full_txt = f"{title or ''} {text or ''}".lower()
            if not re.search(r"\b(internship|interns?|pasant[ií]as?|pasante)\b", full_txt):
                return "Full-time"
        return c_clean

    combined = f"{title or ''} {text or ''}".lower()

    if re.search(r"\b(internship|interns?|pasant[ií]as?|pasante)\b", combined):
        return "Internship"
    if re.search(r"\b(part-time|part time|medio tiempo)\b", combined):
        return "Part-time"
    if re.search(r"\b(full-time|full time|tiempo completo)\b", combined):
        return "Full-time"

    return "Not specified"


def extract_department(title: str, text: str, department: Optional[str] = None) -> str:
    if department and department.strip() and department.strip().lower() not in ("not specified", "no especificada", ""):
        return department.strip()

    combined = f"{title or ''} {text or ''}".lower()

    if re.search(r"\b(sales|ventas|account executive|commercial|comercial)\b", combined):
        return "Sales"
    if re.search(r"\b(hr|rrhh|human resources|recursoshumanos|recruiting|recruiter|talent)\b", combined):
        return "RRHH"
    if re.search(r"\b(qa|quality assurance|testing|tester)\b", combined):
        return "QA"
    if re.search(r"\b(data|data engineer|analytics|machine learning|ai)\b", combined):
        return "Data"
    if re.search(r"\b(support|soporte|it support|helpdesk)\b", combined):
        return "IT Support"
    if re.search(r"\b(software|engineering|developer|desarrollador|backend|frontend|fullstack|c\+\+|python|node|sistemas)\b", combined):
        return "Software Engineering"

    return "Not specified"


def build_unified_job_dict(
    title: str,
    company: str,
    location: str,
    work_mode: str,
    commitment: str,
    salary_range: str,
    key_technologies: List[str],
    main_requirements: List[str],
    summary: str,
    raw_text: str,
    language: str,
    source_page: str,
    source_url: Optional[str] = None,
    job_id: Optional[str] = None,
    department: Optional[str] = None,
    seniority: Optional[str] = None,
    years_of_experience: Optional[Any] = None,
    application_method: Optional[str] = None,
    status: str = "pending_ranking"
) -> dict:
    """Constructs a standardized, unified job dictionary matching the jobs.json schema."""
    assigned_id = _generate_stable_job_id(
        title=title,
        company=company,
        summary=summary,
        source_page=source_page,
        source_url=source_url,
        job_id=job_id
    )

    norm_years_exp = years_of_experience if (years_of_experience and str(years_of_experience).lower() not in ("undefined", "none", "null", "")) else extract_years_of_experience(title=title, text=raw_text)
    norm_commitment = extract_commitment(title=title, text=raw_text, commitment=commitment)
    norm_department = extract_department(title=title, text=raw_text, department=department)
    norm_seniority = extract_seniority(title=title, text=raw_text, seniority=seniority, years_of_exp=norm_years_exp)
    norm_app_method = _extract_application_method(text=raw_text or summary, source_url=source_url, application_method=application_method, company=company, job_id=assigned_id)

    final_url = source_url.strip() if (source_url and str(source_url).strip().lower() not in ("none", "null", "")) else None
    if not final_url and "Postulación web en: " in norm_app_method:
        extracted_u = norm_app_method.replace("Postulación web en: ", "").strip()
        if extracted_u.startswith("http"):
            final_url = extracted_u

    return {
        "id": assigned_id,
        "created_at": datetime.now().isoformat(),
        "title": title.strip() if title else "Untitled",
        "company": company.strip() if company else "Not specified",
        "location": location.strip() if location else "Not specified",
        "work_mode": work_mode.strip() if work_mode else "Not specified",
        "commitment": norm_commitment,
        "department": norm_department,
        "seniority": norm_seniority,
        "years_of_experience": norm_years_exp,
        "salary_range": salary_range.strip() if salary_range else "Not specified",
        "key_technologies": key_technologies if isinstance(key_technologies, list) else [],
        "main_requirements": main_requirements if isinstance(main_requirements, list) else [],
        "summary": summary.strip() if summary else "",
        "raw_text": raw_text.strip() if raw_text else (summary.strip() if summary else title),
        "language": language.lower().strip() if language else "en",
        "source_page": source_page.strip() if source_page else "Manual",
        "source_url": final_url,
        "application_method": norm_app_method,
        "status": status,
        "score": None,
        "justification": None,
        "strengths": [],
        "gaps": [],
        "ranked_at": None,
        "user_notes": None
    }




def save_multiple_jobs_json(job_dicts: List[dict]) -> dict:
    """
    Saves a list of standardized job dictionaries to jobs.json in batch with deduplication and upsert.

    Returns:
        Dict with saved_count, updated_count, and list of saved job IDs.
    """
    if not job_dicts:
        return {"saved_count": 0, "updated_count": 0, "saved_jobs": []}

    try:
        if JOBS_FILE_PATH.exists():
            with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                try:
                    jobs = json.load(f)
                    if not isinstance(jobs, list):
                        jobs = []
                except json.JSONDecodeError:
                    jobs = []
        else:
            jobs = []

        existing_ids = {str(j.get("id", "")).lower(): j for j in jobs if j.get("id")}
        saved_jobs = []
        updated_count = 0

        for jdict in job_dicts:
            jid = str(jdict.get("id", "")).lower()
            if not jid or jid in ("none", "null", "undefined", ""):
                continue

            if jid in existing_ids:
                # Upsert existing job without destroying user metadata (e.g. user_notes, status, score, justification)
                target = existing_ids[jid]
                for key in (
                    "title", "company", "location", "work_mode", "commitment", "department",
                    "seniority", "years_of_experience", "salary_range", "key_technologies",
                    "main_requirements", "summary", "raw_text", "language", "source_page",
                    "source_url", "application_method"
                ):
                    val = jdict.get(key)
                    if val is not None and val != "" and val != "Not specified" and val != "undefined":
                        target[key] = val

                if not target.get("status") or target.get("status") in ("undefined", "null", "none", ""):
                    target["status"] = jdict.get("status", "new")
                updated_count += 1
            else:
                if not jdict.get("status"):
                    jdict["status"] = "new"
                jobs.append(jdict)
                existing_ids[jid] = jdict
                saved_jobs.append(jdict)

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return {
            "saved_count": len(saved_jobs),
            "updated_count": updated_count,
            "saved_jobs": saved_jobs
        }
    except Exception as e:
        return {"error": str(e), "saved_count": 0, "updated_count": 0, "saved_jobs": []}


def save_job_json(
    title: str,
    company: str,
    location: str,
    work_mode: str,
    salary_range: str,
    key_technologies: List[str],
    main_requirements: List[str],
    summary: str,
    language: str,
    commitment: str = "Not specified",
    department: Optional[str] = None,
    seniority: Optional[str] = None,
    source_page: str = "Manual",
    source_url: Optional[str] = None,
    job_id: Optional[str] = None,
    application_method: Optional[str] = None,
    raw_text: Optional[str] = None
) -> str:
    """
    Saves a parsed and structured job position to jobs.json with deduplication and complete raw text.
    """
    new_job = build_unified_job_dict(
        title=title,
        company=company,
        location=location,
        work_mode=work_mode,
        commitment=commitment,
        department=department,
        seniority=seniority,
        salary_range=salary_range,
        key_technologies=key_technologies,
        main_requirements=main_requirements,
        summary=summary,
        raw_text=raw_text if raw_text else summary,
        language=language,
        source_page=source_page,
        source_url=source_url,
        job_id=job_id,
        application_method=application_method
    )



    from src.tools.queries import evaluate_post_parse_filters
    passed, reason = evaluate_post_parse_filters(new_job)
    if not passed:
        return (
            f"FilteredByPostParse: Position '{title}' at '{company}' (ID: {new_job['id']}) "
            f"was discarded without saving to jobs.json. Reason: {reason}"
        )


    res = save_multiple_jobs_json([new_job])
    if res.get("saved_count", 0) > 0:
        return f"Success: Position '{title}' at '{company}' saved to jobs.json with ID {new_job['id']}."
    else:
        return f"AlreadyExists: Position '{title}' at '{company}' (ID: {new_job['id']}) is already saved in jobs.json."


# Alias for backwards compatibility
guardar_empleo_json = save_job_json


