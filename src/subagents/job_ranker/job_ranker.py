"""
Definition of the JobRanker Subagent.

This subagent reads the candidate's profile (candidate_profile.md), evaluates job position fit (0-100),
persists the score via update_job_ranking_json, and generates a formatted response in the position's language.
"""

from pathlib import Path
from google.adk.agents import Agent
from src.config import DEFAULT_MODEL
from src.subagents.job_ranker.tools import read_candidate_profile, update_job_ranking_json, save_ranked_jobs_batch

GUIDELINES_PATH = Path(__file__).parent / "guidelines.md"
with open(GUIDELINES_PATH, "r", encoding="utf-8") as f:
    job_ranker_instruction = f.read()

job_ranker_agent = Agent(
    name="job_ranker_agent",
    model=DEFAULT_MODEL,
    description=(
        "Expert subagent for evaluating fit match and ranking job positions (0 to 100) "
        "against the candidate's professional profile (profile/candidate_profile.md). "
        "Use this agent whenever evaluating, rating, or ranking job positions."
    ),
    instruction=job_ranker_instruction,
    tools=[read_candidate_profile, update_job_ranking_json, save_ranked_jobs_batch]
)

