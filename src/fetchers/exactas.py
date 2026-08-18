"""
Exactas UBA job board scraper for JobBud.
Scrapes active job postings from the Faculty of Exact and Natural Sciences (UBA),
normalizes them to List[JobDict] via parser subagent, and provides the agent tool.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.subagents.job_parser.tools import _generate_stable_job_id

EXACTAS_BOARD_URL = (
    "https://exactas.uba.ar/ofertas-de-trabajo-profesional/ofertas-activas-estudiantes/"
)


def fetch_exactas_jobs(url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches active job postings from Exactas UBA job board
    and normalizes each posting into a standardized JobDict via the parser subagent.

    Args:
        url: Optional board URL (defaults to official student job board).

    Returns:
        List of normalized JobDict objects.
    """
    target_url = url.strip() if url and str(url).strip() else EXACTAS_BOARD_URL
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(target_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        main = soup.find("div", class_="hentry") or soup.find("div", id="content") or soup
        text = main.get_text("\n", strip=True)

        offers_raw = re.split(r'(?=Oferta\s*#)', text)
        offers = [off.strip() for off in offers_raw if off.startswith("Oferta #")]

        if not offers:
            return []

        from src.subagents.job_pipeline.adk_clients import parse_raw_text_with_adk

        job_dicts: List[Dict[str, Any]] = []
        for off in offers:
            # Parse text with the parser subagent
            jdict = parse_raw_text_with_adk(
                f"Página Origen: Exactas UBA\nURL Origen: {target_url}\n\n{off}"
            )
            jdict["source_page"] = "Exactas UBA"
            jdict["source_url"] = target_url
            jdict["id"] = _generate_stable_job_id(
                title=jdict.get("title", ""),
                company=jdict.get("company", ""),
                summary=off[:300],
                source_page="Exactas UBA",
                source_url=target_url,
                job_id=jdict.get("id"),
            )
            jdict["status"] = "new"
            job_dicts.append(jdict)

        return job_dicts

    except Exception:
        return []


def fetch_exactas_job_board(url: Optional[str] = None) -> str:
    """
    Agent tool: Fetches active job postings from Exactas UBA job board,
    applies hard pre-filters (Stage 2), and sets the in-memory candidate cache.

    Args:
        url: Optional board URL.

    Returns:
        Formatted text summary and candidates listing for user interaction.
    """
    target_url = url.strip() if url and str(url).strip() else EXACTAS_BOARD_URL
    all_jobs = fetch_exactas_jobs(target_url)
    if not all_jobs:
        return "No se encontraron ofertas activas en la bolsa de trabajo de Exactas UBA en este momento."

    from src.tools.queries import load_blacklist_terms, filter_job_by_location

    terms = load_blacklist_terms()
    retained_jobs: List[Dict[str, Any]] = []
    discarded_summary: List[str] = []

    for job in all_jobs:
        j_id = job.get("id", "exactas")
        j_title = job.get("title", "Oferta")
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

        retained_jobs.append(job)

    # Update in-memory cache with retained jobs and stats
    from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache

    set_last_fetched_jobs_cache(
        retained_jobs,
        total_raw=len(all_jobs),
        pre_discarded_summary=discarded_summary,
    )

    # Format response markdown
    now_str = datetime.now().strftime("%d/%m/%Y a las %H:%M hs")
    res_lines = [
        f"🔍 **Tablero de Exactas UBA** (Actualizado al {now_str}):\n",
        f"📊 **Resumen del Pre-Filtro Duro (Etapa 2 - 0 Tokens)**:",
        f"- **Total de ofertas detectadas en el portal**: {len(all_jobs)}",
        f"- **Ofertas pre-descartadas automáticamente**: {len(discarded_summary)}",
        f"- **Ofertas conservadas para evaluación**: {len(retained_jobs)}\n",
    ]

    if discarded_summary:
        res_lines.append("🚫 **Detalle de ofertas descartadas en Pre-Filtro**:")
        res_lines.extend(discarded_summary[:10])
        if len(discarded_summary) > 10:
            res_lines.append(f"- *...y {len(discarded_summary) - 10} ofertas más descartadas.*")
        res_lines.append("")

    if not retained_jobs:
        res_lines.append("⚠️ *No se encontraron vacantes que superen el pre-filtro de ubicación y perfil.*")
        return "\n".join(res_lines)

    res_lines.append("📋 **Vacantes Conservadas**:")
    for idx, j in enumerate(retained_jobs, 1):
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
