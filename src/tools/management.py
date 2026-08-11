"""
Job status management, deletion, and action reversion tools for JobBud.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
JOBS_FILE_PATH = ROOT_DIR / "jobs.json"
BACKUP_FILE_PATH = ROOT_DIR / ".last_job_action_backup.json"


def _save_action_backup(action_type: str, job_id: str, previous_job_state: dict, new_status: Optional[str] = None):
    backup_data = {
        "action_type": action_type,
        "job_id": job_id,
        "previous_job_state": previous_job_state,
        "new_status": new_status,
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open(BACKUP_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def mark_job_status(identifier: str, status: str, notes: Optional[str] = None) -> str:
    """
    Updates the status of a job position in jobs.json (e.g., to 'disqualified', 'applied', 'ranked', or 'pending_ranking').

    Args:
        identifier: Job ID (e.g. "exactas_86_26", "linkedin_4445031526"), title, or URL.
        status: Target status ('disqualified' / 'descartada', 'applied' / 'aplicada', 'ranked', 'pending_ranking').
        notes: Optional user notes or explanation for the status change.

    Returns:
        Confirmation message specifying position title, ID, previous status, new status, and prompt for reversion.
    """
    if not JOBS_FILE_PATH.exists():
        return "Error: No jobs.json file found."

    status_map = {
        "disqualified": "disqualified",
        "descartada": "disqualified",
        "descalificada": "disqualified",
        "applied": "applied",
        "aplicada": "applied",
        "postuladas": "applied",
        "ranked": "ranked",
        "pending_ranking": "pending_ranking"
    }

    normalized_status = status_map.get(status.strip().lower(), status.strip().lower())

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        clean_id = identifier.strip().lower()
        found_idx = None
        for i, j in enumerate(jobs):
            j_id = str(j.get("id", "")).lower()
            j_title = str(j.get("title", "")).lower()
            j_url = str(j.get("source_url", "")).lower()

            if clean_id == j_id or clean_id == j_title or (clean_id in j_url and len(clean_id) > 10):
                found_idx = i
                break

        if found_idx is None:
            exactas_match = re.search(r'(\d+[\/\-_]\d+)', clean_id)
            if exactas_match:
                target_num = exactas_match.group(1).replace('/', '_').replace('-', '_')
                for i, j in enumerate(jobs):
                    if target_num in str(j.get("id", "")).lower():
                        found_idx = i
                        break

        if found_idx is None:
            return f"Error: No position found matching '{identifier}' in jobs.json."

        target_job = jobs[found_idx]
        previous_status = target_job.get("status", "unknown")
        job_title = target_job.get("title", "Desconocida")
        job_id = target_job.get("id", "Desconocido")

        _save_action_backup("mark_status", job_id, dict(target_job), normalized_status)

        target_job["status"] = normalized_status
        target_job["updated_at"] = datetime.now().isoformat()
        if notes:
            target_job["user_notes"] = notes

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return (
            f"Success: La posición '{job_title}' (ID: {job_id}) ha cambiado de estado de '{previous_status}' a '{normalized_status}'."
        )

    except Exception as e:
        return f"Error updating job status: {str(e)}"


def delete_job_from_json(identifier: str) -> str:
    """
    Deletes a job position from jobs.json.

    Args:
        identifier: Job ID (e.g. "exactas_86_26", "linkedin_4445031526"), title, or URL.

    Returns:
        Confirmation message specifying position title, ID, previous status, and prompt for reversion.
    """
    if not JOBS_FILE_PATH.exists():
        return "Error: No jobs.json file found."

    try:
        with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        clean_id = identifier.strip().lower()
        found_idx = None
        for i, j in enumerate(jobs):
            j_id = str(j.get("id", "")).lower()
            j_title = str(j.get("title", "")).lower()
            j_url = str(j.get("source_url", "")).lower()

            if clean_id == j_id or clean_id == j_title or (clean_id in j_url and len(clean_id) > 10):
                found_idx = i
                break

        if found_idx is None:
            exactas_match = re.search(r'(\d+[\/\-_]\d+)', clean_id)
            if exactas_match:
                target_num = exactas_match.group(1).replace('/', '_').replace('-', '_')
                for i, j in enumerate(jobs):
                    if target_num in str(j.get("id", "")).lower():
                        found_idx = i
                        break

        if found_idx is None:
            return f"Error: No position found matching '{identifier}' in jobs.json."

        deleted_job = jobs.pop(found_idx)
        job_title = deleted_job.get("title", "Desconocida")
        job_id = deleted_job.get("id", "Desconocido")
        previous_status = deleted_job.get("status", "unknown")

        _save_action_backup("delete", job_id, deleted_job)

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return (
            f"Success: La posición '{job_title}' (ID: {job_id}) que estaba en estado '{previous_status}' ha sido ELIMINADA de jobs.json."
        )

    except Exception as e:
        return f"Error deleting job position: {str(e)}"


def revert_last_job_action() -> str:
    """
    Reverts the last status change or deletion performed on jobs.json.

    Returns:
        Confirmation message detailing the reverted action, position title, ID, and restored status.
    """
    if not BACKUP_FILE_PATH.exists():
        return "Error: No hay ninguna acción reciente disponible para revertir."

    try:
        with open(BACKUP_FILE_PATH, "r", encoding="utf-8") as f:
            backup = json.load(f)

        action_type = backup.get("action_type")
        job_id = backup.get("job_id")
        previous_job_state = backup.get("previous_job_state", {})

        if not previous_job_state or not job_id:
            return "Error: Los datos del respaldo están incompletos para revertir."

        if not JOBS_FILE_PATH.exists():
            jobs = []
        else:
            with open(JOBS_FILE_PATH, "r", encoding="utf-8") as f:
                jobs = json.load(f)

        job_title = previous_job_state.get("title", "Desconocida")
        restored_status = previous_job_state.get("status", "unknown")

        if action_type == "delete":
            jobs.append(previous_job_state)
            msg = f"ReversionSuccessful: Se ha revertido la eliminación. La posición '{job_title}' (ID: {job_id}) ha sido restaurada con su estado original '{restored_status}'."
        elif action_type == "mark_status":
            found = False
            for i, j in enumerate(jobs):
                if j.get("id") == job_id:
                    jobs[i] = previous_job_state
                    found = True
                    break
            if not found:
                jobs.append(previous_job_state)
            msg = f"ReversionSuccessful: Se ha revertido el cambio de estado. La posición '{job_title}' (ID: {job_id}) ha vuelto a su estado anterior '{restored_status}'."
        else:
            return "Error: Tipo de acción no reconocido en el respaldo."

        with open(JOBS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        try:
            BACKUP_FILE_PATH.unlink()
        except Exception:
            pass

        return msg

    except Exception as e:
        return f"Error reverting last action: {str(e)}"


def execute_job_pipeline_tool(job_items_or_selection: str) -> str:
    """
    Executes the deterministic sequential job processing pipeline (Parse -> Post-Parse Filter -> Batch Rank -> Save).

    Args:
        job_items_or_selection: Selection string (e.g. "1, 3", "del 1 al 4", "todas") or JSON list of job objects.

    Returns:
        Formatted markdown report with filtering and batch ranking results.
    """
    import json
    from src.subagents.job_pipeline import run_job_processing_pipeline

    try:
        raw_str = job_items_or_selection.strip() if isinstance(job_items_or_selection, str) else str(job_items_or_selection)
        if raw_str.startswith("[") or raw_str.startswith("{"):
            data = json.loads(raw_str)
            if isinstance(data, dict):
                data = [data]
        else:
            data = raw_str

        res = run_job_processing_pipeline(data)
        banner = f"⚙️ **[Sequential Pipeline Executed via execute_job_pipeline_tool]**\n\n"
        return banner + res.get("report_markdown", "Pipeline execution completed.")
    except Exception as e:
        return f"Error in sequential pipeline execution: {str(e)}"


def execute_multi_board_pipeline_tool(scope: str = "unanalyzed") -> str:
    """
    Executes the automated multi-board sequential pipeline over registered job boards in profile/board_urls.json.

    Args:
        scope: Filtering criteria for board selection:
               - "unanalyzed" / "nunca": Only boards never analyzed (default).
               - "all" / "todos": All registered boards.
               - Board indices / ranges: "1, 2, 6, 8", "del 1 al 5", "1-5", "1, 3, 5-7" (1-indexed from list_job_boards).
               - "1d" / "dia", "1w" / "semana", "1m" / "mes", "12h", "3d", "2w": Relative timeframes.
               - ISO Date / Timestamp (e.g. "2026-08-01" or "2026-08-01T12:00:00"): Boards not analyzed since cutoff date.
               - Directional prefixes ("desde:2026-08-01", "after:2026-08-01", "hasta:2026-08-01"): Filter boards analyzed after/before date.

    Returns:
        Formatted markdown report with multi-board stats, board timer details, and Top 5 recommendations found.
    """
    from src.subagents.job_pipeline.runner import run_multi_board_pipeline

    try:
        res = run_multi_board_pipeline(scope_str=scope)
        banner = f"🌐 **[Automated Multi-Board Pipeline Executed via execute_multi_board_pipeline_tool]**\n\n"
        return banner + res.get("report_markdown", "Multi-board pipeline execution completed.")
    except Exception as e:
        return f"Error in multi-board pipeline execution: {str(e)}"




