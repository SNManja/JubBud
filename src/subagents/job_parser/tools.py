"""
Tools specific to the JobParser subagent.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
JOBS_FILE_PATH = ROOT_DIR / "jobs.json"


def _generate_stable_job_id(
    title: str,
    company: str,
    summary: str,
    source_page: str,
    source_url: Optional[str],
    job_id: Optional[str] = None
) -> str:
    """Generates a stable, deterministic job ID based on source and job details."""
    if job_id and job_id.strip():
        cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '_', job_id.strip())
        return cleaned.lower()

    text_to_search = f"{title} {summary} {source_url or ''}"

    # 1. Exactas UBA format: Oferta #86/26 or 86/2026 or 86-26
    exactas_match = re.search(r'Oferta\s*#?\s*(\d+[\/\-_]\d+)', text_to_search, re.IGNORECASE)
    if exactas_match:
        num_part = exactas_match.group(1).replace('/', '_').replace('-', '_')
        return f"exactas_{num_part}"

    exactas_match_simple = re.search(r'Oferta\s*#?\s*(\d+)', text_to_search, re.IGNORECASE)
    if source_page and "exactas" in source_page.lower() and exactas_match_simple:
        return f"exactas_{exactas_match_simple.group(1)}"

    # 2. LinkedIn ID from URL or text
    if source_url:
        linkedin_match = re.search(r'(?:view/|jobid[=_]|currentJobId=)(\d+)', source_url, re.IGNORECASE)
        if linkedin_match:
            return f"linkedin_{linkedin_match.group(1)}"

    if source_page and "linkedin" in source_page.lower() and source_url:
        linkedin_match2 = re.search(r'(\d{9,11})', source_url)
        if linkedin_match2:
            return f"linkedin_{linkedin_match2.group(1)}"

    # 3. Deterministic hash fallback for manual or un-ID'd postings
    raw_key = f"{company.strip().lower()}:{title.strip().lower()}"
    hash_hex = hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:8]
    prefix = "exactas" if (source_page and "exactas" in source_page.lower()) else ("linkedin" if (source_page and "linkedin" in source_page.lower()) else "manual")
    return f"{prefix}_{hash_hex}"


def _extract_application_method(text: str, source_url: Optional[str], application_method: Optional[str] = None) -> str:
    if application_method and application_method.strip():
        return application_method.strip()

    full_text = text or ""
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', full_text)
    ref_match = re.search(r'(?:referencia|ref[:\s]*)(.*)', full_text, re.IGNORECASE)

    if email_match:
        email = email_match.group(0)
        ref_text = f" (Ref: {ref_match.group(1).strip()})" if ref_match else ""
        return f"Enviar CV por correo a {email}{ref_text}"

    if source_url and source_url.strip():
        return f"Postulación web en: {source_url.strip()}"

    return "No especificado en el aviso"


def extract_seniority(title: str, text: str, seniority: Optional[str] = None) -> str:
    if seniority and seniority.strip() and seniority.strip().lower() not in ("not specified", "no especificada", "desconocida", ""):
        return seniority.strip()

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

    app_method = _extract_application_method(raw_text or summary, source_url, application_method)
    detected_seniority = extract_seniority(title, raw_text or summary, seniority)
    detected_department = extract_department(title, raw_text or summary, department)

    return {
        "id": assigned_id,
        "created_at": datetime.now().isoformat(),
        "title": title.strip() if title else "Untitled",
        "company": company.strip() if company else "Not specified",
        "location": location.strip() if location else "Not specified",
        "work_mode": work_mode.strip() if work_mode else "Not specified",
        "commitment": commitment.strip() if commitment else "Not specified",
        "department": detected_department,
        "seniority": detected_seniority,
        "salary_range": salary_range.strip() if salary_range else "Not specified",
        "key_technologies": key_technologies if isinstance(key_technologies, list) else [],
        "main_requirements": main_requirements if isinstance(main_requirements, list) else [],
        "summary": summary.strip() if summary else "",
        "raw_text": raw_text.strip() if raw_text else (summary.strip() if summary else title),
        "language": language.lower().strip() if language else "en",
        "source_page": source_page.strip() if source_page else "Manual",
        "source_url": source_url,
        "application_method": app_method,
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
    Saves a list of standardized job dictionaries to jobs.json in batch with deduplication.

    Returns:
        Dict with saved_count, skipped_count, and list of saved job IDs.
    """
    if not job_dicts:
        return {"saved_count": 0, "skipped_count": 0, "saved_jobs": []}

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

        existing_ids = {str(j.get("id", "")).lower() for j in jobs}
        saved_jobs = []
        skipped_count = 0

        for jdict in job_dicts:
            jid = str(jdict.get("id", "")).lower()
            if jid in existing_ids:
                skipped_count += 1
            else:
                jobs.append(jdict)
                existing_ids.add(jid)
                saved_jobs.append(jdict)

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return {
            "saved_count": len(saved_jobs),
            "skipped_count": skipped_count,
            "saved_jobs": saved_jobs
        }
    except Exception as e:
        return {"error": str(e), "saved_count": 0, "skipped_count": 0, "saved_jobs": []}


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


