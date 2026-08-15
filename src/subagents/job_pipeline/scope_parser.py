"""
Scope parsing and board filtering utilities for multi-board execution in JobBud.
Supports index ranges, relative times (e.g. '1d', '3d'), ISO dates, and keyword filters.
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


def _parse_board_indices(scope_str: str, total_boards: int) -> List[int]:
    """
    Parses selection string for 1-indexed board positions (e.g. "1,2,6,8", "del 1 al 5", "1-5", "1, 3, 5-7").
    Returns 0-indexed integer indices to select from sorted boards list.
    """
    indices = set()
    sc = scope_str.strip().lower()

    range_matches = list(re.finditer(r'(?:del\s*)?(\d+)\s*(?:a|al|-)\s*(\d+)', sc))
    for rm in range_matches:
        start_idx = int(rm.group(1))
        end_idx = int(rm.group(2))
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        for i in range(start_idx, end_idx + 1):
            if 1 <= i <= total_boards:
                indices.add(i - 1)

    sc_clean = re.sub(r'(?:del\s*)?\d+\s*(?:a|al|-)\s*\d+', '', sc)
    single_digits = re.findall(r'\b\d+\b', sc_clean)
    for d in single_digits:
        val = int(d)
        if 1 <= val <= total_boards:
            indices.add(val - 1)

    return sorted(list(indices))


def filter_boards_by_scope(
    boards: List[Dict[str, Any]], scope_str: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filters a list of board objects based on scope criteria:
    - 'unanalyzed' / 'nunca' / 'nuevos': Only boards where last_analyzed is None.
    - 'all' / 'todos': All registered boards.
    - Board index list / ranges (e.g. '1, 2, 6, 8', 'del 1 al 5', '1-5'): Specific 1-indexed boards.
    - Relative time ('1d', '3d', '12h', '2w', '1m'): Boards not analyzed in timeframe (or never analyzed).
    - ISO Date / Timestamp (e.g. '2026-08-01'): Boards not analyzed since cutoff date.
    - Directional prefixes: 'after:YYYY-MM-DD' or 'desde:YYYY-MM-DD', 'before:YYYY-MM-DD' or 'hasta:YYYY-MM-DD'.
    """
    if not boards:
        return []

    sc = scope_str.strip().lower() if scope_str else "unanalyzed"

    if sc in ("unanalyzed", "nunca", "nuevos", "un-analyzed", "sin_analizar"):
        return [b for b in boards if not b.get("last_analyzed")]
    if sc in ("all", "todos", "todas", "*", "completo"):
        return list(boards)

    is_date_or_time = bool(
        re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', sc)
        or any(
            sc.startswith(p)
            for p in ("after:", "desde:", "posterior:", "before:", "hasta:", "anterior:")
        )
        or re.search(
            r'\d+\s*(?:[dhwm]|min|día|dias|días|hora|horas|semana|semanas|mes|meses)\b', sc
        )
    )

    if not is_date_or_time:
        if re.search(r'\b\d+\b', sc) or re.search(r'\d+\s*-\s*\d+', sc):
            selected_indices = _parse_board_indices(sc, len(boards))
            if selected_indices:
                return [boards[i] for i in selected_indices if 0 <= i < len(boards)]

    comparison = "before"
    if sc.startswith("after:") or sc.startswith("desde:") or sc.startswith("posterior:"):
        comparison = "after"
        sc = re.sub(r'^(after:|desde:|posterior:)', '', sc).strip()
    elif sc.startswith("before:") or sc.startswith("hasta:") or sc.startswith("anterior:"):
        comparison = "before"
        sc = re.sub(r'^(before:|hasta:|anterior:)', '', sc).strip()

    now = datetime.now()
    cutoff = None

    # Try parsing as ISO / standard date formats (e.g. 2026-08-01, 2026-08-01T12:00:00, 2026/08/01)
    clean_date = sc.replace("/", "-").replace(" ", "T")
    try:
        if len(clean_date) == 10 and clean_date.count("-") == 2:
            cutoff = datetime.fromisoformat(clean_date + "T00:00:00")
        else:
            cutoff = datetime.fromisoformat(clean_date)
    except ValueError:
        pass

    if cutoff is None:
        if any(w in sc for w in ("dia", "day")) and not re.search(r'\d+[hwm]', sc):
            num_match = re.search(r'(\d+)', sc)
            days = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(days=days)
        elif any(w in sc for w in ("semana", "week")) and not re.search(r'\d+[hdm]', sc):
            num_match = re.search(r'(\d+)', sc)
            weeks = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(weeks=weeks)
        elif any(w in sc for w in ("mes", "month")) and not re.search(r'\d+[hdw]', sc):
            num_match = re.search(r'(\d+)', sc)
            months = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(days=months * 30)
        elif any(w in sc for w in ("hora", "hour")) and not re.search(r'\d+[dwm]', sc):
            num_match = re.search(r'(\d+)', sc)
            hours = int(num_match.group(1)) if num_match else 1
            cutoff = now - timedelta(hours=hours)
        else:
            match = re.search(r'(\d+)\s*([dhwm]|min)?', sc)
            if match:
                num = int(match.group(1))
                unit = match.group(2) or "d"
                if unit == "h":
                    cutoff = now - timedelta(hours=num)
                elif unit == "w":
                    cutoff = now - timedelta(weeks=num)
                elif unit == "m" and "min" not in sc:
                    cutoff = now - timedelta(days=num * 30)
                elif "min" in sc:
                    cutoff = now - timedelta(minutes=num)
                else:
                    cutoff = now - timedelta(days=num)

    if cutoff is None:
        return [b for b in boards if not b.get("last_analyzed")]

    filtered = []
    for b in boards:
        last_an = b.get("last_analyzed")
        if not last_an:
            if comparison == "before":
                filtered.append(b)
        else:
            try:
                dt = datetime.fromisoformat(last_an)
                if comparison == "after" and dt >= cutoff:
                    filtered.append(b)
                elif comparison == "before" and dt <= cutoff:
                    filtered.append(b)
            except Exception:
                if comparison == "before":
                    filtered.append(b)

    return filtered
