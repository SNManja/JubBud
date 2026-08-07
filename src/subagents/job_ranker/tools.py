"""
Tools specific to the JobRanker subagent.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parents[3]
PROFILE_FILE_PATH = ROOT_DIR / "profile" / "candidate_profile.md"
JOBS_FILE_PATH = ROOT_DIR / "jobs.json"


def read_candidate_profile() -> str:
    """
    Reads and returns the content of the candidate's professional profile (candidate_profile.md).

    Returns:
        Markdown content of the candidate profile.
    """
    try:
        if not PROFILE_FILE_PATH.exists():
            return "Error: candidate_profile.md file not found in profile/ directory."

        with open(PROFILE_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return "Warning: Candidate profile file candidate_profile.md is empty."

        return content
    except Exception as e:
        return f"Error reading candidate profile: {str(e)}"




def update_job_ranking_json(
    job_id: str,
    score: int,
    justification: str,
    strengths: List[str],
    gaps: List[str]
) -> str:
    """
    Updates a job position in jobs.json with its fit score (0-100), justification,
    strengths, and gaps.

    Args:
        job_id: Unique job identifier in jobs.json (or "latest" / "ultimo").
        score: Integer score from 0 to 100 representing fit level.
        justification: Concise explanation of why this score was awarded.
        strengths: List of strong matching points.
        gaps: List of missing skills, gaps, or concerns.

    Returns:
        Confirmation message of the update.
    """
    try:
        if not JOBS_FILE_PATH.exists():
            return "Error: jobs.json file does not exist."

        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        if not isinstance(jobs, list) or len(jobs) == 0:
            return "Error: jobs.json is empty. Position must be saved first."

        target_job = None
        if job_id and job_id.lower() not in ["latest", "ultimo"]:
            for job in jobs:
                if job.get("id") == job_id:
                    target_job = job
                    break

        if target_job is None:
            target_job = jobs[-1]

        target_job["score"] = max(0, min(100, int(score)))
        target_job["justification"] = justification
        target_job["strengths"] = strengths
        target_job["gaps"] = gaps
        target_job["status"] = "ranked"
        target_job["ranked_at"] = datetime.now().isoformat()

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return (
            f"Success: Position '{target_job.get('title')}' (ID: {target_job.get('id')}) "
            f"updated with a score of {target_job['score']}/100 and status 'ranked'."
        )

    except Exception as e:
        return f"Error updating ranking in jobs.json: {str(e)}"


def save_ranked_jobs_batch(ranked_jobs: List[dict]) -> str:
    """
    Saves a batch of fully evaluated and ranked job dictionaries to jobs.json in one atomic operation.

    Args:
        ranked_jobs: List of job dictionaries, each containing complete schema fields plus score, justification, strengths, gaps.

    Returns:
        Confirmation message summarizing saved positions.
    """
    if not ranked_jobs:
        return "Error: No ranked jobs provided to save."

    try:
        jobs = []
        if JOBS_FILE_PATH.exists():
            with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                try:
                    jobs = json.load(f)
                    if not isinstance(jobs, list):
                        jobs = []
                except Exception:
                    jobs = []

        from src.tools.queries import evaluate_post_parse_filters

        VALID_SCHEMA_KEYS = {
            "id", "created_at", "title", "company", "location", "work_mode", "commitment",
            "department", "seniority", "salary_range", "key_technologies", "main_requirements",
            "summary", "raw_text", "language", "source_page", "source_url", "application_method",
            "user_notes", "status", "ranked_at", "score", "justification", "strengths", "gaps"
        }

        existing_ids = {str(j.get("id", "")).lower(): j for j in jobs}
        saved_titles = []
        discarded_titles = []

        for rjob in ranked_jobs:
            passed, reason = evaluate_post_parse_filters(rjob)
            if not passed:
                discarded_titles.append(f"'{rjob.get('title')}' ({reason})")
                continue

            jid = str(rjob.get("id", "")).strip().lower()
            if not jid or jid in ("none", "null", "undefined"):
                continue

            score_val = max(0, min(100, int(rjob.get("score", 0))))
            just_val = str(rjob.get("justification", ""))
            str_val = rjob.get("strengths", []) if isinstance(rjob.get("strengths"), list) else []
            gaps_val = rjob.get("gaps", []) if isinstance(rjob.get("gaps"), list) else []
            now_iso = datetime.now().isoformat()

            if jid in existing_ids:
                # ONLY update ranker evaluation fields; keep source fields completely untouched
                target = existing_ids[jid]
                target["score"] = score_val
                target["justification"] = just_val
                target["strengths"] = str_val
                target["gaps"] = gaps_val
                target["status"] = "ranked"
                target["ranked_at"] = now_iso
                # Clean any non-schema attributes if present
                for k in list(target.keys()):
                    if k not in VALID_SCHEMA_KEYS:
                        del target[k]
                saved_titles.append(f"'{target.get('title')}' ({score_val}/100)")
            else:
                # New job being saved with ranking: sanitize to valid schema keys only
                sanitized_job = {k: v for k, v in rjob.items() if k in VALID_SCHEMA_KEYS}
                sanitized_job["score"] = score_val
                sanitized_job["justification"] = just_val
                sanitized_job["strengths"] = str_val
                sanitized_job["gaps"] = gaps_val
                sanitized_job["status"] = "ranked"
                sanitized_job["ranked_at"] = now_iso
                if not sanitized_job.get("created_at"):
                    sanitized_job["created_at"] = now_iso

                jobs.append(sanitized_job)
                existing_ids[jid] = sanitized_job
                saved_titles.append(f"'{sanitized_job.get('title')}' ({score_val}/100)")


        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return f"Success: Saved {len(saved_titles)} ranked position(s) to jobs.json: {', '.join(saved_titles)}."

    except Exception as e:
        return f"Error saving ranked batch to jobs.json: {str(e)}"


# Aliases for backwards compatibility
leer_perfil_candidato = read_candidate_profile
actualizar_ranking_json = update_job_ranking_json

