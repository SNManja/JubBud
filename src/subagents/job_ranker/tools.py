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

        existing_ids = {str(j.get("id", "")).lower(): j for j in jobs}
        saved_titles = []
        discarded_titles = []

        for rjob in ranked_jobs:
            passed, reason = evaluate_post_parse_filters(rjob)
            if not passed:
                discarded_titles.append(f"'{rjob.get('title')}' ({reason})")
                continue

            jid = str(rjob.get("id", "")).lower()
            rjob["status"] = "ranked"
            if not rjob.get("ranked_at"):
                rjob["ranked_at"] = datetime.now().isoformat()

            if jid in existing_ids:
                existing_ids[jid].update(rjob)
            else:
                jobs.append(rjob)
                existing_ids[jid] = rjob

            saved_titles.append(f"'{rjob.get('title')}' ({rjob.get('score')}/100)")


        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return f"Success: Saved {len(saved_titles)} ranked position(s) to jobs.json: {', '.join(saved_titles)}."

    except Exception as e:
        return f"Error saving ranked batch to jobs.json: {str(e)}"


# Aliases for backwards compatibility
leer_perfil_candidato = read_candidate_profile
actualizar_ranking_json = update_job_ranking_json

