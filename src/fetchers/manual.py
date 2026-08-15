"""
Manual text ingestion fetcher for JobBud.
Takes unparsed raw text provided by the user in chat and normalizes it to [JobDict].
"""

from typing import List, Dict, Any, Optional
from src.subagents.job_parser.tools import _generate_stable_job_id


def ingest_manual_job(raw_text: str, source_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Ingests and normalizes user-provided raw job text into a single-element list [JobDict].

    Args:
        raw_text: Unstructured raw job text from user prompt.
        source_url: Optional URL where the job was found.

    Returns:
        List containing the single normalized JobDict.
    """
    cleaned_text = (raw_text or "").strip()
    if not cleaned_text:
        return []

    from src.subagents.job_pipeline.adk_clients import parse_raw_text_with_adk

    job_dict = parse_raw_text_with_adk(cleaned_text)
    job_dict["source_page"] = "Manual"
    if source_url:
        job_dict["source_url"] = source_url

    job_dict["id"] = _generate_stable_job_id(
        title=job_dict.get("title", ""),
        company=job_dict.get("company", ""),
        summary=job_dict.get("summary", ""),
        source_page="Manual",
        source_url=source_url,
    )

    return [job_dict]
