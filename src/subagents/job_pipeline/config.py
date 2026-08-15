"""
Configuration loader for JobBud's job processing pipeline.
Reads profile/pipeline_config.json with safe fallbacks.
"""

import json
from pathlib import Path
from typing import Dict, Any

ROOT_DIR = Path(__file__).resolve().parents[3]
PIPELINE_CONFIG_PATH = ROOT_DIR / "profile" / "pipeline_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "max_jobs_per_board": None,
    "delay_between_batches_seconds": 3.0,
    "delay_between_boards_seconds": 10.0,
    "max_years_experience": 3,
    "auto_pipeline_execution": True,
}


def load_pipeline_config() -> Dict[str, Any]:
    """
    Reads configuration settings from profile/pipeline_config.json with safe fallbacks.

    Returns:
        Dict containing max_jobs_per_board, delay_between_batches_seconds,
        delay_between_boards_seconds, max_years_experience, and auto_pipeline_execution.
    """
    if not PIPELINE_CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    try:
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        if not isinstance(cfg, dict):
            return dict(DEFAULT_CONFIG)

        raw_cap = cfg.get("max_jobs_per_board")
        parsed_cap = (
            int(raw_cap)
            if raw_cap is not None and str(raw_cap).lower() not in ("none", "null", "")
            else None
        )

        return {
            "max_jobs_per_board": parsed_cap,
            "delay_between_batches_seconds": float(cfg.get("delay_between_batches_seconds", 3.0)),
            "delay_between_boards_seconds": float(cfg.get("delay_between_boards_seconds", 10.0)),
            "max_years_experience": int(cfg.get("max_years_experience", 3)),
            "auto_pipeline_execution": bool(cfg.get("auto_pipeline_execution", True)),
        }
    except Exception:
        return dict(DEFAULT_CONFIG)
