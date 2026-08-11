"""
Tools specific to the JobRanker subagent.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
PROFILE_FILE_PATH = ROOT_DIR / "profile" / "candidate_profile.md"
POLICY_FILE_PATH = ROOT_DIR / "profile" / "ranking_policy.md"
JOBS_FILE_PATH = ROOT_DIR / "jobs.json"


def read_ranking_policy() -> str:
    """
    Reads and returns the content of the configurable ranking policy (profile/ranking_policy.md).

    Returns:
        Markdown content of the ranking policy.
    """
    try:
        if not POLICY_FILE_PATH.exists():
            return "Error: ranking_policy.md file not found in profile/ directory."

        with open(POLICY_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return "Warning: Ranking policy file ranking_policy.md is empty."

        return content
    except Exception as e:
        return f"Error reading ranking policy: {str(e)}"


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
    Updates an existing job position in jobs.json with its fit score (0-100), justification,
    strengths, and gaps. Requires an explicit job_id.

    Args:
        job_id: Explicit unique job identifier in jobs.json.
        score: Integer score from 0 to 100 representing fit level.
        justification: Concise explanation of why this score was awarded.
        strengths: List of strong matching points.
        gaps: List of missing skills, gaps, or concerns.

    Returns:
        Confirmation message of the update.
    """
    try:
        clean_id = str(job_id).strip().lower() if job_id else ""
        if not clean_id or clean_id in ("none", "null", "undefined"):
            return "Error: An explicit job_id is required."

        if not JOBS_FILE_PATH.exists():
            return "Error: jobs.json file not found."

        try:
            with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                jobs = json.load(f)
                if not isinstance(jobs, list):
                    return "Error: jobs.json exists but is not a valid JSON list."
        except Exception as e:
            return f"Error reading jobs.json (file may be corrupted): {str(e)}"

        target_job = None
        for j in jobs:
            if str(j.get("id", "")).strip().lower() == clean_id:
                target_job = j
                break

        if not target_job:
            return f"Error: Job with ID '{job_id}' not found in jobs.json."

        if score is None:
            return "Error: Score parameter is required."

        try:
            score_val = int(score)
        except (TypeError, ValueError):
            return f"Error: Score '{score}' is not a valid integer."

        if not (0 <= score_val <= 100):
            return f"Error: Score {score_val} is outside 0-100."

        target_job["score"] = score_val
        target_job["justification"] = str(justification)
        target_job["strengths"] = list(strengths) if isinstance(strengths, list) else []
        target_job["gaps"] = list(gaps) if isinstance(gaps, list) else []
        target_job["status"] = "ranked"
        target_job["ranked_at"] = datetime.now().isoformat()

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return f"Success: Job '{target_job.get('title')}' updated with score {score_val}/100 and status 'ranked'."

    except Exception as e:
        return f"Error updating job ranking in jobs.json: {str(e)}"


_RANKING_BATCH_CACHE: dict[str, dict] = {}


def set_ranking_batch_cache(chunk: List[dict]):
    """Sets the transient in-memory batch cache of complete unranked jobs for the active ranking chunk."""
    global _RANKING_BATCH_CACHE
    _RANKING_BATCH_CACHE = {str(j.get("id", "")).strip().lower(): dict(j) for j in chunk if isinstance(j, dict) and j.get("id")}


def clear_ranking_batch_cache():
    """Clears the transient in-memory batch cache after ranking chunk completes."""
    global _RANKING_BATCH_CACHE
    _RANKING_BATCH_CACHE.clear()


def save_ranked_jobs_batch(ranked_jobs: List[dict]) -> str:
    """
    Merges LLM evaluation results with complete jobs in active batch cache and persists to jobs.json.

    Args:
        ranked_jobs: List of job dicts returned by the LLM ranker containing score, justification, strengths, gaps.

    Returns:
        Confirmation message summarizing saved jobs and any persistence errors.
    """
    if not ranked_jobs or not isinstance(ranked_jobs, list):
        return "Error: No ranked jobs provided to update."

    try:
        jobs = []
        if JOBS_FILE_PATH.exists():
            try:
                with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                    jobs = json.load(f)
                    if not isinstance(jobs, list):
                        return "Error: jobs.json exists but is not a valid JSON list."
            except Exception as e:
                return f"Error reading jobs.json (file may be corrupted): {str(e)}"

        existing_ids = {str(j.get("id", "")).strip().lower() for j in jobs if j.get("id")}
        updated_titles = []
        errors = []

        for rjob in ranked_jobs:
            raw_id = rjob.get("id")
            jid = str(raw_id).strip().lower() if raw_id else ""
            if not jid or jid in ("none", "null", "undefined"):
                errors.append("Ranking persistence error: ranked job is missing a valid ID.")
                continue

            if jid not in _RANKING_BATCH_CACHE:
                errors.append(f"Ranking persistence error: ranking result '{jid}' does not belong to the active ranking batch.")
                continue

            if jid in existing_ids:
                errors.append(f"Ranking persistence error: position '{jid}' already exists in jobs.json and cannot be re-persisted by automatic batch ranking.")
                continue

            score_raw = rjob.get("score")
            if score_raw is None:
                errors.append(f"Ranking persistence error: result '{jid}' is missing score.")
                continue

            try:
                score_val = int(score_raw)
            except (TypeError, ValueError):
                errors.append(f"Ranking persistence error: result '{jid}' has an invalid score '{score_raw}'.")
                continue

            if not (0 <= score_val <= 100):
                errors.append(f"Ranking persistence error: result '{jid}' has score {score_val} outside 0-100.")
                continue

            just_val = str(rjob.get("justification", ""))
            str_val = rjob.get("strengths", []) if isinstance(rjob.get("strengths"), list) else []
            gaps_val = rjob.get("gaps", []) if isinstance(rjob.get("gaps"), list) else []
            now_iso = datetime.now().isoformat()

            original_job = dict(_RANKING_BATCH_CACHE[jid])
            original_job["score"] = score_val
            original_job["justification"] = just_val
            original_job["strengths"] = str_val
            original_job["gaps"] = gaps_val
            original_job["status"] = "ranked"
            original_job["ranked_at"] = now_iso

            jobs.append(original_job)
            existing_ids.add(jid)

            updated_titles.append(f"'{original_job.get('title')}' ({score_val}/100)")

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        total_attempted = len(ranked_jobs)
        num_updated = len(updated_titles)
        num_errors = len(errors)

        if num_updated == 0 and num_errors > 0:
            return f"Error: Failed to update any of the {total_attempted} position(s). Errors: {'; '.join(errors)}"
        elif num_errors > 0:
            return (
                f"Partial success: Updated {num_updated}/{total_attempted} ranked position(s) in jobs.json: "
                f"{', '.join(updated_titles)}. Errors: {'; '.join(errors)}"
            )
        else:
            return f"Success: Updated {num_updated} ranked position(s) in jobs.json: {', '.join(updated_titles)}."

    except Exception as e:
        return f"Error updating ranked batch in jobs.json: {str(e)}"


# Aliases for backwards compatibility
leer_perfil_candidato = read_candidate_profile
leer_politica_ranking = read_ranking_policy
actualizar_ranking_json = update_job_ranking_json
