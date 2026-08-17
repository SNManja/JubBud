"""
Configuration loader for JobBud's job processing pipeline.
Reads profile/pipeline_config.json with safe fallbacks.
"""

import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
PIPELINE_CONFIG_PATH = ROOT_DIR / "profile" / "pipeline_config.json"

SUPPORTED_LANGUAGES = {"es", "en"}

DEFAULT_CONFIG: Dict[str, Any] = {
    "language": None,
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
        Dict containing language, max_jobs_per_board, delay_between_batches_seconds,
        delay_between_boards_seconds, max_years_experience, and auto_pipeline_execution.
    """
    if not PIPELINE_CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    try:
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        if not isinstance(cfg, dict):
            return dict(DEFAULT_CONFIG)

        # Validate language preference
        raw_lang = cfg.get("language")
        valid_lang = (
            raw_lang.strip().lower()
            if isinstance(raw_lang, str) and raw_lang.strip().lower() in SUPPORTED_LANGUAGES
            else None
        )

        raw_cap = cfg.get("max_jobs_per_board")
        parsed_cap = (
            int(raw_cap)
            if raw_cap is not None and str(raw_cap).lower() not in ("none", "null", "")
            else None
        )

        return {
            "language": valid_lang,
            "max_jobs_per_board": parsed_cap,
            "delay_between_batches_seconds": float(cfg.get("delay_between_batches_seconds", 3.0)),
            "delay_between_boards_seconds": float(cfg.get("delay_between_boards_seconds", 10.0)),
            "max_years_experience": int(cfg.get("max_years_experience", 3)),
            "auto_pipeline_execution": bool(cfg.get("auto_pipeline_execution", True)),
        }
    except Exception:
        return dict(DEFAULT_CONFIG)


def set_pipeline_config_language(language: str) -> Tuple[bool, str]:
    """
    Persists the user's preferred language in profile/pipeline_config.json.

    Args:
        language: Language code ('es' or 'en').

    Returns:
        Tuple of (success: bool, message: str).
    """
    lang_clean = language.strip().lower() if isinstance(language, str) else ""
    if lang_clean not in SUPPORTED_LANGUAGES:
        return False, f"Idioma no soportado: '{language}'. Idiomas válidos: {', '.join(sorted(SUPPORTED_LANGUAGES))}."

    try:
        cfg: Dict[str, Any] = {}
        if PIPELINE_CONFIG_PATH.exists():
            with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    cfg = {}

        cfg["language"] = lang_clean
        with open(PIPELINE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

        return True, f"Idioma configurado y persistido correctamente como '{lang_clean}'."
    except Exception as e:
        return False, f"Error al persistir idioma en {PIPELINE_CONFIG_PATH}: {str(e)}"

