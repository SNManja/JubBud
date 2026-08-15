"""
Board Management Tools for JobBud.

Manages persistent user job board registries (profile/board_urls.json) with deterministic
sorting (oldest/never analyzed first) and automated board analysis delegation.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BOARD_URLS_PATH = ROOT_DIR / "profile" / "board_urls.json"


def _load_board_urls() -> List[Dict[str, Any]]:
    if not BOARD_URLS_PATH.exists():
        return []
    try:
        with open(BOARD_URLS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_board_urls(boards: List[Dict[str, Any]]) -> bool:
    try:
        BOARD_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BOARD_URLS_PATH, "w", encoding="utf-8") as f:
            json.dump(boards, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _sort_boards_deterministically(boards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sorts board objects deterministically:
    1. Boards never analyzed (last_analyzed is None) first, sorted by created_at then name.
    2. Boards analyzed least recently (oldest last_analyzed timestamp) next.
    3. Tie-breaker by board name (lowercase).
    """
    def sort_key(b: Dict[str, Any]):
        last_an = b.get("last_analyzed")
        created = b.get("created_at") or "9999-99-99T99:99:99"
        name = str(b.get("name", "")).lower()
        # Non-analyzed boards get empty string for last_analyzed to sort first
        last_str = "" if not last_an else str(last_an)
        return (last_str, created, name)

    return sorted(boards, key=sort_key)


def add_board_url(name: str, url: str, notes: Optional[str] = None) -> str:
    """
    Registers a new job board URL in profile/board_urls.json.

    Args:
        name: Short descriptive name for the board (e.g. "AppsFlyer", "Mercado Libre").
        url: Full URL of the job board (e.g. "https://boards.greenhouse.io/appsflyer").
        notes: Optional notes or description.

    Returns:
        Confirmation message with assigned board ID.
    """
    clean_url = url.strip()
    clean_name = name.strip()
    if not clean_url or not clean_name:
        return "Error: Both board name and URL are required."

    source_type = "greenhouse" if "greenhouse" in clean_url.lower() else ("ashby" if "ashby" in clean_url.lower() else "web")
    board_id = f"board_{re.sub(r'[^a-zA-Z0-9_]', '', clean_name.lower())}"

    boards = _load_board_urls()

    # Check duplicate URL or ID
    for b in boards:
        if b.get("url", "").lower() == clean_url.lower():
            return f"AlreadyExists: Board with URL '{clean_url}' is already registered as '{b.get('name')}' (ID: {b.get('id')})."

    new_board = {
        "id": board_id,
        "name": clean_name,
        "url": clean_url,
        "source_type": source_type,
        "last_analyzed": None,
        "created_at": datetime.now().isoformat(),
        "notes": notes.strip() if notes else ""
    }

    boards.append(new_board)
    if _save_board_urls(boards):
        return f"Success: Registered job board '{clean_name}' (ID: {board_id}, Type: {source_type}) in profile/board_urls.json."
    else:
        return f"Error: Failed to save board to profile/board_urls.json."


def _format_friendly_date(iso_str: Optional[str]) -> str:
    """
    Formats ISO timestamp string into a friendly date representation in Spanish.
    """
    if not iso_str:
        return "**Nunca**"

    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now()
        diff_days = (now.date() - dt.date()).days
        date_formatted = dt.strftime("%d/%m/%Y a las %H:%M hs")

        if diff_days == 0:
            return f"Hoy ({date_formatted})"
        elif diff_days == 1:
            return f"Ayer ({date_formatted})"
        else:
            return f"El {date_formatted} (hace {diff_days} días)"
    except Exception:
        return str(iso_str)[:16].replace("T", " ")


def list_job_boards() -> str:
    """
    Lists all registered job boards numbered 1 to N, sorted deterministically by oldest/least recently analyzed first.

    Returns:
        Formatted string listing all boards with their index number, name, last_analyzed date/time, and URL.
    """
    boards = _load_board_urls()
    if not boards:
        return "No job boards currently registered in profile/board_urls.json. You can add one using add_board_url."

    sorted_boards = _sort_boards_deterministically(boards)

    lines = [
        "📋 **Tus Tableros de Empleo Registrados (Ordenados de más antiguo/no analizado a más reciente):**\n"
    ]

    for idx, b in enumerate(sorted_boards, start=1):
        last_an = b.get("last_analyzed")
        last_str = _format_friendly_date(last_an)
        lines.append(f"{idx}. **{b.get('name')}** (ID: `{b.get('id')}`) — Último análisis: {last_str}\n   URL: {b.get('url')}")

    lines.append("\n💡 *Puedes analizar cualquier tablero indicando su número (ej. 'analizar el board 1') o su nombre.*")
    return "\n".join(lines)



def get_board_to_analyze(identifier: str) -> str:
    """
    Resolves a job board by its 1-indexed number, ID, or name, updates its last_analyzed timestamp to now(), and fetches its postings.

    Args:
        identifier: Number (e.g. "1", "2"), ID (e.g. "board_appsflyer"), or name (e.g. "AppsFlyer").

    Returns:
        Result string from board fetcher or error message.
    """
    boards = _load_board_urls()
    if not boards:
        return "Error: No job boards registered in profile/board_urls.json. Please add a board first."

    sorted_boards = _sort_boards_deterministically(boards)
    clean_id = identifier.strip().lower()

    selected_board = None

    # Case A: Numeric 1-indexed selection
    if clean_id.isdigit():
        idx = int(clean_id)
        if 1 <= idx <= len(sorted_boards):
            selected_board = sorted_boards[idx - 1]

    # Case B: Match by board ID or name
    if not selected_board:
        for b in sorted_boards:
            if b.get("id", "").lower() == clean_id or b.get("name", "").lower() == clean_id:
                selected_board = b
                break

    # Case C: Substring match by name
    if not selected_board:
        for b in sorted_boards:
            if clean_id in b.get("name", "").lower():
                selected_board = b
                break

    if not selected_board:
        return (
            f"Error: Could not find job board matching '{identifier}'. "
            f"Please run list_job_boards to see valid boards and indices (1 to {len(sorted_boards)})."
        )

    # Update last_analyzed timestamp deterministically
    now_str = datetime.now().isoformat()
    selected_board["last_analyzed"] = now_str

    # Write back updated timestamp to profile/board_urls.json
    for b in boards:
        if b.get("id") == selected_board.get("id"):
            b["last_analyzed"] = now_str
            break
    _save_board_urls(boards)

    url = selected_board.get("url")
    stype = selected_board.get("source_type", "greenhouse")

    if stype == "greenhouse" or "greenhouse" in url.lower():
        from src.fetchers import fetch_greenhouse_job_content
        fetch_res = fetch_greenhouse_job_content(url)
        return f"🔍 **Analizando Tablero '{selected_board.get('name')}'** (Último análisis actualizado a {now_str[:16].replace('T', ' ')}):\n\n{fetch_res}"
    elif stype == "ashby" or "ashby" in url.lower():
        from src.fetchers import fetch_ashby_job_content
        fetch_res = fetch_ashby_job_content(url)
        return f"🔍 **Analizando Tablero '{selected_board.get('name')}'** (Último análisis actualizado a {now_str[:16].replace('T', ' ')}):\n\n{fetch_res}"
    else:
        return f"Board URL resolved: {url}. Please analyze position details."


def delete_board_url(identifier: str) -> str:
    """
    Deletes a registered job board by its 1-indexed number, ID, or name.

    Args:
        identifier: Number (e.g. "1"), ID, or name of the board to remove.

    Returns:
        Confirmation message.
    """
    boards = _load_board_urls()
    if not boards:
        return "Error: No job boards registered in profile/board_urls.json."

    sorted_boards = _sort_boards_deterministically(boards)
    clean_id = identifier.strip().lower()

    selected_board = None

    if clean_id.isdigit():
        idx = int(clean_id)
        if 1 <= idx <= len(sorted_boards):
            selected_board = sorted_boards[idx - 1]

    if not selected_board:
        for b in sorted_boards:
            if b.get("id", "").lower() == clean_id or b.get("name", "").lower() == clean_id:
                selected_board = b
                break

    if not selected_board:
        return f"Error: Board matching '{identifier}' was not found."

    boards = [b for b in boards if b.get("id") != selected_board.get("id")]
    _save_board_urls(boards)
    return f"Success: Removed job board '{selected_board.get('name')}' (ID: {selected_board.get('id')}) from profile/board_urls.json."
