"""
Base utilities, text compressors, and helpers for JobBud fetchers.
"""

import re
from typing import List

TECH_PATTERNS = [
    r"C\+\+", "Python", "JavaScript", "TypeScript", r"Node\.js", "Node",
    "Go", "Golang", "Rust", "Java", "React", "Vue", "Angular", "SQL",
    "PostgreSQL", "MongoDB", "Docker", "Kubernetes", "AWS", "GCP", "Azure",
    "Kafka", "Redis", "Linux"
]


def compress_job_text(text: str) -> str:
    """
    Strips non-essential legal footers (EEO disclaimers, privacy notices)
    while preserving 100% of job requirements, responsibilities, benefits, and technologies.
    """
    if not text or len(text) < 300:
        return text or ""

    sections_to_drop = [
        r"(?i)equal opportunity employer.*",
        r"(?i)we are an equal opportunity employer.*",
        r"(?i)applicant privacy notice.*",
        r"(?i)california consumer privacy.*",
    ]

    cleaned = text
    for pattern in sections_to_drop:
        cleaned = re.sub(pattern, "", cleaned)

    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    res = "\n".join(lines)
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res.strip()


def extract_technologies_from_text(text: str) -> List[str]:
    """Scans text for common core technologies and returns matching keyword list."""
    if not text:
        return []
    found_techs = []
    for tech in TECH_PATTERNS:
        clean_tech = tech.replace("\\", "")
        if re.search(r"\b" + tech + r"\b", text, re.IGNORECASE):
            if clean_tech not in found_techs:
                found_techs.append(clean_tech)
    return found_techs
