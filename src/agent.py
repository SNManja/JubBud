"""
Main JobBud Agent Definition in Google ADK.
"""

from pathlib import Path
from google.adk.agents import Agent
from src.config import DEFAULT_MODEL
from src.tools import HERRAMIENTAS_BASICAS
from src.subagents.job_parser.job_parser import job_parser_agent
from src.subagents.job_ranker.job_ranker import job_ranker_agent

GUIDELINES_PATH = Path(__file__).parent / "guidelines.md"
with open(GUIDELINES_PATH, "r", encoding="utf-8") as f:
    jobbud_instruction = f.read()

# JobBud Main Agent (Job Search Assistant & Master Orchestrator)
jobbud_agent = Agent(
    name="jobbud_agent",
    model=DEFAULT_MODEL,
    description="An AI assistant specialized in job search optimization, position analysis, and career matching.",
    instruction=jobbud_instruction,
    tools=HERRAMIENTAS_BASICAS,
    sub_agents=[job_parser_agent, job_ranker_agent]
)

# Export root_agent for ADK Web compatibility
root_agent = jobbud_agent
