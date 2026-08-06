import html
import re
import requests
from bs4 import BeautifulSoup
from src.tools.queries import load_blacklist_terms



def compress_job_text(text: str) -> str:

    """
    Strips non-essential boilerplate sections (EEO, corporate descriptions, legal footers)
    to save prompt tokens while preserving all core job requirements, responsibilities, and technologies.
    """
    if not text or len(text) < 300:
        return text

    sections_to_drop = [
        r"(?i)equal opportunity employer.*",
        r"(?i)we are an equal opportunity employer.*",
        r"(?i)applicant privacy notice.*",
        r"(?i)california consumer privacy.*",
        r"(?i)about canonical.*",
        r"(?i)about appsflyer.*",
        r"(?i)what we offer.*"
    ]

    cleaned = text
    for pattern in sections_to_drop:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)

    lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
    res = "\n".join(lines)
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res.strip()


def fetch_linkedin_job_content(url: str) -> str:

    """
    Attempts to fetch and extract the text content of a job posting from a LinkedIn URL.

    Args:
        url: The LinkedIn job URL provided by the user.

    Returns:
        The extracted raw text of the job description if successful,
        or an error message indicating that automated access was blocked and manual text entry is needed.
    """
    cleaned_url = url.strip()
    if not re.search(r"linkedin\.com/jobs", cleaned_url, re.IGNORECASE) and "linkedin.com" not in cleaned_url.lower():
        return "Error: The provided URL does not appear to be a valid LinkedIn job posting URL."

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    try:
        response = requests.get(cleaned_url, headers=headers, timeout=10, allow_redirects=True)
        if response.status_code != 200:
            return (
                f"Could not automatically retrieve the job posting content from LinkedIn (HTTP Status {response.status_code}). "
                "LinkedIn security or login barriers prevented reading the page. "
                "Please copy and paste the job text directly into the chat."
            )

        html_content = response.text

        meta_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html_content, re.IGNORECASE)
        meta_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html_content, re.IGNORECASE)

        title_text = meta_title.group(1) if meta_title else ""
        desc_text = meta_desc.group(1) if meta_desc else ""

        desc_container = re.search(r'class=["\'][^"\']*show-more-less-html__markup[^"\']*["\'][^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
        if desc_container:
            container_text = re.sub(r'<[^>]+>', ' ', desc_container.group(1))
            container_text = ' '.join(container_text.split())
            if len(container_text) > 100:
                desc_text = container_text

        combined_text = f"Title: {title_text}\nDescription: {desc_text}".strip()

        if len(combined_text) < 50 or ("Sign in" in combined_text and len(desc_text) < 30):
            return (
                "Could not extract meaningful job details from the LinkedIn URL due to access or authentication restrictions. "
                "Please copy and paste the job description text directly into the chat so JobBud can parse and rank it."
            )

        return (
            f"Source Page: LinkedIn\nSource URL: {cleaned_url}\n\n"
            f"LinkedIn Job Post Content Extracted:\n\n{combined_text}"
        )

    except Exception as e:
        return (
            f"An error occurred while fetching the URL ({str(e)}). "
            "Please copy and paste the job description text directly into the chat."
        )


def fetch_exactas_job_board() -> str:
    """
    Fetches active job postings from the Faculty of Exact and Natural Sciences (UBA) job board
    (https://exactas.uba.ar/ofertas-de-trabajo-profesional/ofertas-activas-estudiantes/)
    and filters for positions relevant to Computer Science (Cs. de la Computación).

    Returns:
        A formatted string containing all matching job offers found for Computer Science students/graduates.
    """
    target_url = "https://exactas.uba.ar/ofertas-de-trabajo-profesional/ofertas-activas-estudiantes/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(target_url, headers=headers, timeout=12)
        if resp.status_code != 200:
            return f"Error: No se pudo acceder a la bolsa de trabajo de Exactas UBA (HTTP Status {resp.status_code})."

        soup = BeautifulSoup(resp.text, "html.parser")
        main = soup.find("div", class_="hentry") or soup.find("div", id="content") or soup
        text = main.get_text("\n", strip=True)

        offers_raw = re.split(r'(?=Oferta\s*#)', text)
        matching_offers = []

        for off in offers_raw:
            if not off.startswith("Oferta #"):
                continue

            off_lower = off.lower()
            is_computacion = (
                "computac" in off_lower or
                "cs. de la computación" in off_lower or
                "sistemas" in off_lower or
                "desarrollador" in off_lower or
                "software" in off_lower or
                "programador" in off_lower or
                "data" in off_lower
            )

            if is_computacion:
                matching_offers.append(off.strip())

        if not matching_offers:
            return "No se encontraron ofertas activas dirigidas a la carrera de Computación en la bolsa de trabajo de Exactas UBA en este momento."

        result = (
            f"Se encontraron {len(matching_offers)} oferta(s) para Computación en la bolsa de trabajo de Exactas UBA.\n"
            f"Página Origen: Exactas UBA\n"
            f"URL Origen: {target_url}\n\n"
        )
        for i, off in enumerate(matching_offers, 1):
            result += f"--- OFERTA {i} (Origen: Exactas UBA, URL: {target_url}) ---\n{off}\n\n"

        from src.tools.queries import filter_jobs_by_blacklist
        return filter_jobs_by_blacklist(result)

    except Exception as e:
        return f"Error al consultar la bolsa de trabajo de Exactas UBA: {str(e)}"



def parse_greenhouse_url(url: str) -> tuple[str | None, str | None]:
    """
    Extracts (board_token, job_id) from a Greenhouse URL.

    Args:
        url: Greenhouse job post or job board URL.

    Returns:
        Tuple of (board_token, job_id). job_id may be None for board-level URLs.
    """
    cleaned_url = url.strip()

    # 1. Direct API endpoint match: e.g. boards-api.greenhouse.io/v1/boards/appsflyer/jobs/123456 or /jobs
    api_match = re.search(r"greenhouse\.io/v1/boards/([^/?&]+)(?:/jobs/(\d+)|/jobs)?", cleaned_url, re.IGNORECASE)
    if api_match:
        return api_match.group(1), api_match.group(2)

    # 2. Query parameters with explicit for & token/gh_jid: e.g. embed/job_detail?for=board_token&token=123456
    for_match = re.search(r"[?&]for=([^&]+)", cleaned_url, re.IGNORECASE)
    token_match = re.search(r"[?&](?:token|gh_jid|job_id)=(\d+)", cleaned_url, re.IGNORECASE)
    if for_match and token_match:
        return for_match.group(1), token_match.group(1)

    # 3. Path match with job ID: e.g. boards.greenhouse.io/canonical/jobs/5647382 or job-boards.greenhouse.io/stripe/jobs/45678
    path_job_match = re.search(r"greenhouse\.io/([^/?]+)/(?:jobs|positions)/(\d+)", cleaned_url, re.IGNORECASE)
    if path_job_match:
        return path_job_match.group(1), path_job_match.group(2)

    # 4. Path match with board token and gh_jid/token query param: e.g. boards.greenhouse.io/canonical?gh_jid=5647382
    board_path_match = re.search(r"greenhouse\.io/([^/?]+)", cleaned_url, re.IGNORECASE)
    if board_path_match and board_path_match.group(1).lower() not in ("embed", "v1", "api", "jobs"):
        board_token = board_path_match.group(1)
        job_id = token_match.group(1) if token_match else None
        return board_token, job_id

    # 5. Fallback for token without explicit board in path
    if token_match and for_match:
        return for_match.group(1), token_match.group(1)

    return None, None




def fetch_greenhouse_job_content(url: str) -> str:
    """
    Fetches job details or job board listings from Greenhouse using the official Greenhouse Public Board API.

    Args:
        url: A Greenhouse job posting URL or job board URL.

    Returns:
        Formatted raw text of the job posting(s) extracted via Greenhouse API.
    """
    import html

    cleaned_url = url.strip()
    board_token, job_id = parse_greenhouse_url(cleaned_url)

    if not board_token:
        return (
            "Error: Could not extract a valid Greenhouse board token or job ID from the provided URL. "
            "Please check the URL or paste the job description text directly."
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    # Case A: Fetch single job posting by job_id
    if job_id:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?content=true"
        try:
            resp = requests.get(api_url, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title", "Unknown Title")
                location_info = data.get("location", {})
                location_name = location_info.get("name", "Not specified") if isinstance(location_info, dict) else str(location_info)
                req_id = data.get("requisition_id", "N/A")
                absolute_url = data.get("absolute_url", cleaned_url)

                departments = ", ".join(d.get("name", "") for d in data.get("departments", []) if d.get("name"))
                offices = ", ".join(o.get("name", "") for o in data.get("offices", []) if o.get("name"))

                raw_content = data.get("content", "")
                decoded_html = html.unescape(raw_content)
                soup = BeautifulSoup(decoded_html, "html.parser")
                clean_description = compress_job_text(soup.get_text("\n", strip=True))

                output_parts = [
                    f"Source Page: Greenhouse",
                    f"Source URL: {absolute_url}",
                    f"Greenhouse Job ID: {job_id}",
                    f"Board Token: {board_token}",
                    f"Title: {title}",
                    f"Company / Board: {board_token}",
                    f"Location: {location_name}",
                ]
                if departments:
                    output_parts.append(f"Department(s): {departments}")
                if offices:
                    output_parts.append(f"Office(s): {offices}")
                if req_id and req_id != "N/A":
                    output_parts.append(f"Requisition ID: {req_id}")

                output_parts.append(f"\nJob Description:\n{clean_description}")

                return "\n".join(output_parts)
            elif resp.status_code == 404:
                return (
                    f"Error: Job ID '{job_id}' was not found on Greenhouse board '{board_token}' (HTTP 404). "
                    "Please verify the job link or paste the text directly."
                )
            else:
                return (
                    f"Error: Failed to fetch Greenhouse job posting (HTTP Status {resp.status_code}). "
                    "Please paste the job text directly."
                )
        except Exception as e:
            return f"Error while connecting to Greenhouse API: {str(e)}"

    # Case B: Fetch board listing when no specific job_id is provided
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return (
                f"Error: Failed to fetch job board '{board_token}' from Greenhouse API (HTTP Status {resp.status_code}). "
                "Please verify the URL or paste the job description directly."
            )

        data = resp.json()
        jobs = data.get("jobs", [])

        if not jobs:
            return f"No active job postings found on Greenhouse board '{board_token}'."

        terms = load_blacklist_terms()
        tech_patterns = [
            r"C\+\+", "Python", "JavaScript", "TypeScript", r"Node\.js", "Node",
            "Go", "Golang", "Rust", "Java", "React", "Vue", "Angular", "SQL",
            "PostgreSQL", "MongoDB", "Docker", "Kubernetes", "AWS", "GCP", "Azure",
            "Kafka", "Redis", "Linux"
        ]

        retained_job_dicts = []
        discarded_summary = []

        for job in jobs:
            j_id = str(job.get("id"))
            j_title = job.get("title", "Untitled")
            j_loc = job.get("location", {}).get("name", "N/A") if isinstance(job.get("location"), dict) else "N/A"
            j_url = job.get("absolute_url", cleaned_url)

            j_deps = ", ".join(d.get("name", "") for d in job.get("departments", []) if d.get("name"))

            # Initial Pre-LLM location check from API metadata
            from src.tools.queries import filter_job_by_location
            pre_loc_passed, pre_loc_reason = filter_job_by_location({"location": j_loc, "work_mode": "Not specified"})
            if not pre_loc_passed:
                discarded_summary.append(f"- **{j_title}** (ID: {j_id}, Ubicación: {j_loc}) — *{pre_loc_reason}*")
                continue

            raw_content = job.get("content", "")
            decoded_html = html.unescape(raw_content)
            soup = BeautifulSoup(decoded_html, "html.parser")
            clean_desc = compress_job_text(soup.get_text("\n", strip=True))

            title_and_dept = f"{j_title} {j_deps}".lower()
            matched_term = None
            for term in terms:
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", title_and_dept):
                    matched_term = term
                    break

            if matched_term:
                discarded_summary.append(f"- **{j_title}** (ID: {j_id}, Área: {j_deps or 'N/A'}) — *Filtrado por: '{matched_term}'*")
            else:
                full_text = f"{j_title}\n{j_loc}\n{clean_desc}"
                full_lower = full_text.lower()
                work_mode = "Remote" if "remote" in full_lower else ("Hybrid" if "hybrid" in full_lower or "híbrido" in full_lower else ("On-site" if "on-site" in full_lower or "onsite" in full_lower else "Not specified"))


                commitment = "Part-time" if "part-time" in full_lower or "part time" in full_lower else ("Full-time" if "full-time" in full_lower or "full time" in full_lower else ("Internship" if "intern" in full_lower or "pasantía" in full_lower else "Not specified"))


                found_techs = []
                for tech in tech_patterns:
                    clean_tech = tech.replace("\\", "")
                    if re.search(r"\b" + tech + r"\b", full_text, re.IGNORECASE):
                        if clean_tech not in found_techs:
                            found_techs.append(clean_tech)

                summary_paras = [p.strip() for p in clean_desc.split("\n\n") if len(p.strip()) > 30]
                summary = summary_paras[0] if summary_paras else clean_desc[:200]

                from src.subagents.job_parser.tools import build_unified_job_dict
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
                    status="pending_ranking"
                )


                from src.tools.queries import filter_job_by_location
                loc_passed, loc_reason = filter_job_by_location(udict)
                if loc_passed:
                    retained_job_dicts.append(udict)
                else:
                    discarded_summary.append(f"- **{j_title}** (ID: {j_id}) — *{loc_reason}*")

        from src.subagents.job_pipeline.runner import set_last_fetched_jobs_cache
        set_last_fetched_jobs_cache(retained_job_dicts)

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
            ""
        ]

        for idx, udict in enumerate(retained_job_dicts, start=1):
            report_parts.append(
                f"{idx}. **[{udict['id']}]** {udict['title']} en *{udict['company']}* — "
                f"Ubicación: {udict['location']} | Modalidad: `{udict['work_mode']}`"
            )

        if discarded_summary:
            report_parts.append(f"\n🚫 **Resumen de vacantes filtradas automáticamente ({len(discarded_summary)}):**")
            report_parts.extend(discarded_summary[:5])
            if len(discarded_summary) > 5:
                report_parts.append(f"... y {len(discarded_summary) - 5} vacante(s) filtradas más.")

        report_parts.append(
            "\n⛔ **NO PROCEDER AL RANKING SIN CONFIRMACIÓN:** El orquestador debe mostrar esta lista al usuario y esperar su elección explícita antes de invocar a `job_ranker_agent`."
        )

        return "\n".join(report_parts)


    except Exception as e:
        return f"Error while fetching Greenhouse job board: {str(e)}"





