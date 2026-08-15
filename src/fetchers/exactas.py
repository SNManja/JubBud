"""
Exactas UBA job board scraper for JobBud.
Scrapes active computer science job postings from the Faculty of Exact and Natural Sciences (UBA),
normalizes them to List[JobDict], and provides the agent tool.
"""

import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

from src.subagents.job_parser.tools import _generate_stable_job_id

EXACTAS_BOARD_URL = (
    "https://exactas.uba.ar/ofertas-de-trabajo-profesional/ofertas-activas-estudiantes/"
)


def fetch_exactas_jobs() -> List[Dict[str, Any]]:
    """
    Fetches active job postings from Exactas UBA job board for Computer Science
    and normalizes each posting into a JobDict via the parser subagent.

    Returns:
        List of normalized JobDict objects.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(EXACTAS_BOARD_URL, headers=headers, timeout=12)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        main = soup.find("div", class_="hentry") or soup.find("div", id="content") or soup
        text = main.get_text("\n", strip=True)

        offers_raw = re.split(r'(?=Oferta\s*#)', text)
        cs_offers = []

        for off in offers_raw:
            if not off.startswith("Oferta #"):
                continue

            off_lower = off.lower()
            is_computacion = (
                "computac" in off_lower
                or "cs. de la computación" in off_lower
                or "sistemas" in off_lower
                or "desarrollador" in off_lower
                or "software" in off_lower
                or "programador" in off_lower
                or "data" in off_lower
            )
            if is_computacion:
                cs_offers.append(off.strip())

        if not cs_offers:
            return []

        from src.subagents.job_pipeline.adk_clients import parse_raw_text_with_adk

        job_dicts: List[Dict[str, Any]] = []
        for off in cs_offers:
            # Parse text with the parser subagent
            jdict = parse_raw_text_with_adk(
                f"Página Origen: Exactas UBA\nURL Origen: {EXACTAS_BOARD_URL}\n\n{off}"
            )
            jdict["source_page"] = "Exactas UBA"
            jdict["source_url"] = EXACTAS_BOARD_URL
            jdict["id"] = _generate_stable_job_id(
                title=jdict.get("title", ""),
                company=jdict.get("company", ""),
                summary=off[:300],
                source_page="Exactas UBA",
                source_url=EXACTAS_BOARD_URL,
            )
            job_dicts.append(jdict)

        return job_dicts

    except Exception:
        return []


def fetch_exactas_job_board() -> str:
    """
    Agent tool: Fetches active job postings from Exactas UBA job board for Computer Science,
    applies hard pre-filters, and sets the in-memory candidate cache.

    Returns:
        A formatted string containing summary statistics and matching job offers for the user.
    """
    all_jobs = fetch_exactas_jobs()
    if not all_jobs:
        return "No se encontraron ofertas activas dirigidas a la carrera de Computación en la bolsa de trabajo de Exactas UBA en este momento."

    from src.tools.queries import load_blacklist_terms, filter_job_by_location

    terms = load_blacklist_terms()
    retained_jobs: List[Dict[str, Any]] = []
    discarded_summary: List[str] = []

    for job in all_jobs:
        j_id = job.get("id", "exactas")
        j_title = job.get("title", "Oferta")
        j_dept = job.get("department", "")

        # 1. Title/Dept blacklist check
        title_and_dept = f"{j_title} {j_dept}".lower()
        matched_term = None
        for term in terms:
            if re.search(r"\b" + re.escape(term.lower()) + r"\b", title_and_dept):
                matched_term = term
                break

        if matched_term:
            discarded_summary.append(
                f"- **{j_title}** (ID: {j_id}) — *Filtrado por: '{matched_term}'*"
            )
            continue

        # 2. Location pre-filter
        loc_passed, loc_reason = filter_job_by_location(job)
        if loc_passed:
            retained_jobs.append(job)
        else:
            discarded_summary.append(f"- **{j_title}** (ID: {j_id}) — *{loc_reason}*")

    from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache

    set_last_fetched_jobs_cache(
        retained_jobs,
        total_raw=len(all_jobs),
        pre_discarded_summary=discarded_summary,
    )

    if not retained_jobs:
        return (
            f"📊 **Bolsa de Empleo Exactas UBA**\n"
            f"- 🔍 **Total de vacantes observadas:** {len(all_jobs)}\n"
            f"- 🚫 **Omitidas por filtros automáticos:** {len(discarded_summary)}\n"
            f"- 📋 **Vacantes conservadas:** 0\n\n"
            f"Ninguna posición superó los filtros iniciales."
        )

    report_parts = [
        f"📊 **Estadísticas de Procesamiento (Exactas UBA)**",
        f"- 🔍 **Total de vacantes observadas:** {len(all_jobs)}",
        f"- 🚫 **Omitidas por filtros automáticos (blacklist / ubicación):** {len(discarded_summary)}",
        f"- 📋 **Vacantes conservadas que superaron los filtros:** {len(retained_jobs)}",
        f"\n❓ **Confirmación Requerida:**",
        f"Se encontraron **{len(retained_jobs)} vacante(s)** válidas. Por favor, confirma cuáles deseas rankear ('todas', '1, 2', etc.):",
        "",
    ]
    for idx, udict in enumerate(retained_jobs, start=1):
        report_parts.append(
            f"{idx}. **[{udict['id']}]** {udict['title']} en *{udict['company']}* — "
            f"Ubicación: {udict['location']} | Modalidad: `{udict['work_mode']}`"
        )

    return "\n".join(report_parts)
