"""
Definition of the JobParser Subagent.

This subagent parses raw job postings, extracts structured data according to guidelines.md,
detects the position language ("es" or "en"), saves it to jobs.json via save_job_json, and returns control to the parent agent.
"""

from pathlib import Path
from google.adk.agents import Agent
from src.config import DEFAULT_MODEL
from src.subagents.job_parser.tools import save_job_json

GUIDELINES_PATH = Path(__file__).parent / "guidelines.md"
with open(GUIDELINES_PATH, "r", encoding="utf-8") as f:
    job_parser_instruction = f.read()

job_parser_agent = Agent(
    name="job_parser_agent",
    model=DEFAULT_MODEL,
    description=(
        "Expert subagent for parsing, structuring, and saving job postings or vacancies. "
        "Use this agent whenever the user asks to process, parse, extract, or save a job posting."
    ),
    instruction=job_parser_instruction,
    tools=[save_job_json]
)
