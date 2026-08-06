"""
Central configuration module for JobBud using Environment Variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Default LLM model for all JobBud agents
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL") or os.getenv("JOBBUD_MODEL") or "gemini-3.1-flash-lite"
