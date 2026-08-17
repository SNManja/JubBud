"""
Report formatting module for JobBud's job pipeline.
Constructs transparent markdown summaries for single-board and multi-board executions.
"""

from typing import List, Dict, Any, Tuple, Optional
from src.subagents.job_pipeline.config import load_pipeline_config

I18N: Dict[str, Dict[str, str]] = {
    "es": {
        "single_title": "📊 **Reporte de Procesamiento de Tablero:**",
        "stage_1": "- 📥 **Vacantes obtenidas en crudo (Etapa 1):** {total_raw}",
        "stage_2": "- 🚫 **Descartadas por filtro pre-parseo duro (Etapa 2):** {pre_discarded_count}",
        "stage_3": "- 📋 **Vacantes válidas post pre-parseo (Etapa 3):** {pre_passed_count}",
        "stage_4_discarded": "- 🚫 **Descartadas por filtro post-parseo (Etapa 4):** {post_discarded_count}",
        "stage_4_deduped": "- ℹ️ **Omitidas por estar analizadas previamente en jobs.json (Etapa 4):** {deduped_count}",
        "stage_4_capped": "- ⏸️ **Omitidas por tope configurado por board (Etapa 4):** {capped_count}",
        "stage_5": "- ⭐ **Vacantes evaluadas y rankeadas con LLM (Etapa 5):** {successfully_ranked_count}{chunk_str}",
        "stage_6": "- 💾 **Vacantes guardadas en jobs.json (Etapa 6):** {successfully_ranked_count}",
        "chunk_batch": " (Lotes de {k} vacantes)",
        "pre_discarded_header": "**Vacantes descartadas en pre-parseo (Etapa 2):**",
        "more_vacancies": "... y {n} vacante(s) más.",
        "post_discarded_header": "**Vacantes descartadas en post-parseo (Etapa 4):**",
        "capped_header": "**Vacantes omitidas por superar el {cap_str} por consulta:**",
        "max_limit": "límite máximo de {max_jobs_per_board}",
        "cap": "tope",
        "fit_eval_header": "**Evaluaciones de Fit (job_ranker_agent):**\n",
        "multi_title": "🌐 **Reporte Consolidado de Procesamiento Multitablero Automático ({scope_str}):**\n",
        "multi_boards": "- 🏢 **Tableros analizados ({count}):** {boards}",
        "multi_timer": "- ⏱️ **Timer entre tableros:** {delay} segundos",
        "multi_top5_header": "🏆 **Top 5 Mejores Oportunidades Encontradas en la Corrida:**\n",
        "multi_no_jobs": "Ninguna posición superó el umbral de filtrado en esta corrida multitablero.",
        "top_fit_prefix": "Fit",
        "top_app_prefix": "Postulación",
    },
    "en": {
        "single_title": "📊 **Job Board Processing Report:**",
        "stage_1": "- 📥 **Raw vacancies retrieved (Stage 1):** {total_raw}",
        "stage_2": "- 🚫 **Discarded by hard pre-parse filter (Stage 2):** {pre_discarded_count}",
        "stage_3": "- 📋 **Valid vacancies post pre-parse (Stage 3):** {pre_passed_count}",
        "stage_4_discarded": "- 🚫 **Discarded by post-parse filter (Stage 4):** {post_discarded_count}",
        "stage_4_deduped": "- ℹ️ **Omitted as already analyzed in jobs.json (Stage 4):** {deduped_count}",
        "stage_4_capped": "- ⏸️ **Omitted due to board cap limit (Stage 4):** {capped_count}",
        "stage_5": "- ⭐ **Vacancies evaluated & ranked with LLM (Stage 5):** {successfully_ranked_count}{chunk_str}",
        "stage_6": "- 💾 **Vacancies saved to jobs.json (Stage 6):** {successfully_ranked_count}",
        "chunk_batch": " (Batches of {k} vacancies)",
        "pre_discarded_header": "**Vacancies discarded in pre-parse (Stage 2):**",
        "more_vacancies": "... and {n} more vacancy/vacancies.",
        "post_discarded_header": "**Vacancies discarded in post-parse (Stage 4):**",
        "capped_header": "**Vacancies omitted for exceeding the {cap_str} per query:**",
        "max_limit": "maximum limit of {max_jobs_per_board}",
        "cap": "cap",
        "fit_eval_header": "**Fit Evaluations (job_ranker_agent):**\n",
        "multi_title": "🌐 **Consolidated Automated Multi-Board Processing Report ({scope_str}):**\n",
        "multi_boards": "- 🏢 **Analyzed boards ({count}):** {boards}",
        "multi_timer": "- ⏱️ **Timer between boards:** {delay} seconds",
        "multi_top5_header": "🏆 **Top 5 Best Opportunities Found in Run:**\n",
        "multi_no_jobs": "No positions passed the filtering threshold in this multi-board run.",
        "top_fit_prefix": "Fit",
        "top_app_prefix": "Application",
    },
}


def _get_lang_dict(lang: Optional[str] = None) -> Dict[str, str]:
    if not lang:
        cfg = load_pipeline_config()
        lang = cfg.get("language")
    lang_clean = (lang or "es").strip().lower()
    return I18N.get(lang_clean, I18N["es"])


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
    language: Optional[str] = None,
) -> str:
    """Generates the transparent 6-stage telemetry markdown report for a single board."""
    t = _get_lang_dict(language)
    chunk_str = t["chunk_batch"].format(k=k) if successfully_ranked_count > 0 else ""

    report_lines = [
        t["single_title"],
        t["stage_1"].format(total_raw=total_raw),
        t["stage_2"].format(pre_discarded_count=pre_discarded_count),
        t["stage_3"].format(pre_passed_count=pre_passed_count),
        t["stage_4_discarded"].format(post_discarded_count=post_discarded_count),
        t["stage_4_deduped"].format(deduped_count=deduped_count),
        t["stage_4_capped"].format(capped_count=capped_count),
        t["stage_5"].format(successfully_ranked_count=successfully_ranked_count, chunk_str=chunk_str),
        t["stage_6"].format(successfully_ranked_count=successfully_ranked_count),
        "",
    ]

    if pre_discarded_summary:
        report_lines.append(t["pre_discarded_header"])
        for item in pre_discarded_summary[:5]:
            report_lines.append(f"  {item}")
        if len(pre_discarded_summary) > 5:
            report_lines.append(f"  {t['more_vacancies'].format(n=len(pre_discarded_summary) - 5)}")
        report_lines.append("")

    if discarded_jobs:
        report_lines.append(t["post_discarded_header"])
        for j, r in discarded_jobs:
            report_lines.append(f"- ❌ **{j.get('title')}** en *{j.get('company')}* — *{r}*")
        report_lines.append("")

    if capped_jobs:
        cap_str = (
            t["max_limit"].format(max_jobs_per_board=max_jobs_per_board)
            if max_jobs_per_board is not None
            else t["cap"]
        )
        report_lines.append(t["capped_header"].format(cap_str=cap_str))
        for j in capped_jobs:
            report_lines.append(f"- ⏸️ **{j.get('title')}** en *{j.get('company')}*")
        report_lines.append("")

    if ranked_results:
        report_lines.append(t["fit_eval_header"])
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
    language: Optional[str] = None,
) -> str:
    """Generates the consolidated markdown report for automated multi-board execution."""
    t = _get_lang_dict(language)

    report_lines = [
        t["multi_title"].format(scope_str=scope_str),
        t["multi_boards"].format(count=len(analyzed_board_names), boards=", ".join(analyzed_board_names)),
        t["multi_timer"].format(delay=delay_between_boards),
        t["stage_1"].format(total_raw=total_raw_sum),
        t["stage_2"].format(pre_discarded_count=total_pre_discarded_sum),
        t["stage_3"].format(pre_passed_count=total_pre_passed_sum),
        t["stage_4_discarded"].format(post_discarded_count=total_post_discarded_sum),
        t["stage_4_deduped"].format(deduped_count=total_deduped_sum),
        t["stage_4_capped"].format(capped_count=total_capped_sum),
        f"- ⭐ {t['stage_5'][4:].format(successfully_ranked_count=total_sent_to_ranker_sum, chunk_str='')}",
        t["stage_6"].format(successfully_ranked_count=total_passed_sum),
        "",
    ]

    if top_5_jobs:
        report_lines.append(t["multi_top5_header"])
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
                report_lines.append(f"   - *{t['top_fit_prefix']}:* {brief_just}...")
            report_lines.append(f"   - *{t['top_app_prefix']}:* {app_method}\n")
    else:
        report_lines.append(t["multi_no_jobs"])

    return "\n".join(report_lines)

