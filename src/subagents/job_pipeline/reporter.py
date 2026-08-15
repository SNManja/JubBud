"""
Report formatting module for JobBud's job pipeline.
Constructs transparent markdown summaries for single-board and multi-board executions.
"""

from typing import List, Dict, Any, Tuple, Optional


def format_single_pipeline_report(
    total_raw: int,
    pre_discarded_count: int,
    pre_passed_count: int,
    post_discarded_count: int,
    deduped_count: int,
    capped_count: int,
    successfully_ranked_count: int,
    k: int = 1,
    pre_discarded_summary: Optional[List[str]] = None,
    discarded_jobs: Optional[List[Tuple[Dict[str, Any], str]]] = None,
    capped_jobs: Optional[List[Dict[str, Any]]] = None,
    max_jobs_per_board: Optional[int] = None,
    ranked_results: Optional[List[Tuple[List[Dict[str, Any]], str]]] = None,
) -> str:
    """Generates the transparent 6-stage telemetry markdown report for a single board."""
    chunk_str = f" (Lotes de {k} vacantes)" if successfully_ranked_count > 0 else ""
    report_lines = [
        "📊 **Reporte de Procesamiento de Tablero:**",
        f"- 📥 **Vacantes obtenidas en crudo (Etapa 1):** {total_raw}",
        f"- 🚫 **Descartadas por filtro pre-parseo duro (Etapa 2):** {pre_discarded_count}",
        f"- 📋 **Vacantes válidas post pre-parseo (Etapa 3):** {pre_passed_count}",
        f"- 🚫 **Descartadas por filtro post-parseo (Etapa 4):** {post_discarded_count}",
        f"- ℹ️ **Omitidas por estar analizadas previamente en jobs.json (Etapa 4):** {deduped_count}",
        f"- ⏸️ **Omitidas por tope configurado por board (Etapa 4):** {capped_count}",
        f"- ⭐ **Vacantes evaluadas y rankeadas con LLM (Etapa 5):** {successfully_ranked_count}{chunk_str}",
        f"- 💾 **Vacantes guardadas en jobs.json (Etapa 6):** {successfully_ranked_count}",
        "",
    ]

    if pre_discarded_summary:
        report_lines.append("**Vacantes descartadas en pre-parseo (Etapa 2):**")
        for item in pre_discarded_summary[:5]:
            report_lines.append(f"  {item}")
        if len(pre_discarded_summary) > 5:
            report_lines.append(f"  ... y {len(pre_discarded_summary) - 5} vacante(s) más.")
        report_lines.append("")

    if discarded_jobs:
        report_lines.append("**Vacantes descartadas en post-parseo (Etapa 4):**")
        for j, r in discarded_jobs:
            report_lines.append(f"- ❌ **{j.get('title')}** en *{j.get('company')}* — *{r}*")
        report_lines.append("")

    if capped_jobs:
        cap_str = (
            f"límite máximo de {max_jobs_per_board}"
            if max_jobs_per_board is not None
            else "tope"
        )
        report_lines.append(f"**Vacantes omitidas por superar el {cap_str} por consulta:**")
        for j in capped_jobs:
            report_lines.append(f"- ⏸️ **{j.get('title')}** en *{j.get('company')}*")
        report_lines.append("")

    if ranked_results:
        report_lines.append("**Evaluaciones de Fit (job_ranker_agent):**\n")
        for _, output_text in ranked_results:
            report_lines.append(output_text)
            report_lines.append("\n---\n")

    return "\n".join(report_lines)


def format_multi_board_report(
    scope_str: str,
    analyzed_board_names: List[str],
    delay_between_boards: float,
    total_raw_sum: int,
    total_pre_discarded_sum: int,
    total_pre_passed_sum: int,
    total_post_discarded_sum: int,
    total_deduped_sum: int,
    total_capped_sum: int,
    total_sent_to_ranker_sum: int,
    total_passed_sum: int,
    top_5_jobs: List[Dict[str, Any]],
) -> str:
    """Generates the consolidated markdown report for automated multi-board execution."""
    report_lines = [
        f"🌐 **Reporte Consolidado de Procesamiento Multitablero Automático ({scope_str}):**\n",
        f"- 🏢 **Tableros analizados ({len(analyzed_board_names)}):** {', '.join(analyzed_board_names)}",
        f"- ⏱️ **Timer entre tableros:** {delay_between_boards} segundos",
        f"- 📥 **Total de vacantes obtenidas en crudo (Etapa 1):** {total_raw_sum}",
        f"- 🚫 **Total descartadas por filtro pre-parseo duro (Etapa 2):** {total_pre_discarded_sum}",
        f"- 📋 **Total vacantes válidas post pre-parseo (Etapa 3):** {total_pre_passed_sum}",
        f"- 🚫 **Total descartadas por filtro post-parseo (Etapa 4):** {total_post_discarded_sum}",
        f"- ℹ️ **Total omitidas por estar analizadas previamente en jobs.json (Etapa 4):** {total_deduped_sum}",
        f"- ⏸️ **Total omitidas por tope configurado por board (Etapa 4):** {total_capped_sum}",
        f"- ⭐ **Total vacantes enviadas al LLM ranker (Etapa 5):** {total_sent_to_ranker_sum}",
        f"- 💾 **Total vacantes guardadas en jobs.json (Etapa 6):** {total_passed_sum}",
        "",
    ]

    if top_5_jobs:
        report_lines.append("🏆 **Top 5 Mejores Oportunidades Encontradas en la Corrida:**\n")
        for rank_idx, j in enumerate(top_5_jobs, start=1):
            score = j.get("score", 0)
            title = j.get("title", "Puesto")
            company = j.get("company", "Empresa")
            wmode = j.get("work_mode", "N/A")
            loc = j.get("location", "N/A")
            justification = j.get("justification", "")
            app_method = j.get("application_method") or j.get("source_url") or "Ver ficha"

            report_lines.append(
                f"{rank_idx}. ⭐ **{score}/100** — **{title}** en *{company}* ({wmode} - {loc})"
            )
            if justification:
                brief_just = justification.split("\n")[0][:180]
                report_lines.append(f"   - *Fit:* {brief_just}...")
            report_lines.append(f"   - *Postulación:* {app_method}\n")
    else:
        report_lines.append("Ninguna posición superó el umbral de filtrado en esta corrida multitablero.")

    return "\n".join(report_lines)
