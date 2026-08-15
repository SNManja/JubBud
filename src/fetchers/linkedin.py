"""
LinkedIn job posting fetcher for JobBud.
Fetches and normalizes a LinkedIn job posting by URL -> returns [JobDict] and provides the agent tool.
"""

import re
import requests
from typing import List, Dict, Any

from src.subagents.job_parser.tools import _generate_stable_job_id


def fetch_linkedin_job(url: str) -> List[Dict[str, Any]]:
    """
    Attempts to fetch and extract a job posting from a LinkedIn URL and normalize it to a JobDict.

    Args:
        url: The LinkedIn job posting URL.

    Returns:
        List containing the single normalized JobDict, or empty list if access was blocked.
    """
    cleaned_url = url.strip()
    if (
        not re.search(r"linkedin\.com/jobs", cleaned_url, re.IGNORECASE)
        and "linkedin.com" not in cleaned_url.lower()
    ):
        return []

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
        response = requests.get(
            cleaned_url, headers=headers, timeout=10, allow_redirects=True
        )
        if response.status_code != 200:
            return []

        html_content = response.text

        meta_title = re.search(
            r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
            html_content,
            re.IGNORECASE,
        )
        meta_desc = re.search(
            r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']',
            html_content,
            re.IGNORECASE,
        )

        title_text = meta_title.group(1) if meta_title else ""
        desc_text = meta_desc.group(1) if meta_desc else ""

        desc_container = re.search(
            r'class=["\'][^"\']*show-more-less-html__markup[^"\']*["\'][^>]*>(.*?)</div>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
        if desc_container:
            container_text = re.sub(r'<[^>]+>', ' ', desc_container.group(1))
            container_text = ' '.join(container_text.split())
            if len(container_text) > 100:
                desc_text = container_text

        combined_text = f"Title: {title_text}\nDescription: {desc_text}".strip()

        if len(combined_text) < 50 or ("Sign in" in combined_text and len(desc_text) < 30):
            return []

        # Parse and normalize using the ADK parser
        from src.subagents.job_pipeline.adk_clients import parse_raw_text_with_adk

        job_dict = parse_raw_text_with_adk(
            f"Source Page: LinkedIn\nSource URL: {cleaned_url}\n\n{combined_text}"
        )
        job_dict["source_page"] = "LinkedIn"
        job_dict["source_url"] = cleaned_url
        job_dict["id"] = _generate_stable_job_id(
            title=job_dict.get("title", ""),
            company=job_dict.get("company", ""),
            summary=job_dict.get("summary", ""),
            source_page="LinkedIn",
            source_url=cleaned_url,
        )

        return [job_dict]

    except Exception:
        return []


def fetch_linkedin_job_content(url: str) -> str:
    """
    Agent tool: Attempts to fetch and extract the content of a job posting from a LinkedIn URL,
    normalizes it to a JobDict, and sets the in-memory cache.

    Args:
        url: The LinkedIn job URL provided by the user.

    Returns:
        The extracted raw text of the job description if successful,
        or an error message indicating that manual text entry is needed.
    """
    cleaned_url = url.strip()
    job_dicts = fetch_linkedin_job(cleaned_url)

    if not job_dicts:
        return (
            "Could not automatically retrieve the job posting content from LinkedIn. "
            "LinkedIn access barriers prevented reading the page. "
            "Please copy and paste the job description text directly into the chat."
        )

    job = job_dicts[0]
    from src.subagents.job_pipeline.state import set_last_fetched_jobs_cache
    set_last_fetched_jobs_cache(job_dicts, total_raw=1, pre_discarded_summary=[])

    return (
        f"Source Page: LinkedIn\n"
        f"Source URL: {job.get('source_url', cleaned_url)}\n\n"
        f"LinkedIn Job Post Content Extracted:\n\n"
        f"Title: {job.get('title')}\n"
        f"Company: {job.get('company')}\n"
        f"Location: {job.get('location')}\n"
        f"Work Mode: {job.get('work_mode')}\n\n"
        f"Job Description:\n{job.get('raw_text')}"
    )
