# JobBud — Project Context & Architecture

## 🎯 Project Goal

JobBud is an intelligent, conversational job-search automation tool designed for a Computer Science student seeking technical roles.

The system receives job postings or listings (from Exactas UBA, LinkedIn, Greenhouse APIs, or manual text), deduplicates and extracts structured information, evaluates and ranks each position against a candidate profile (`profile/candidate_profile.md`), and manages application lifecycles.

The project is built on **Google ADK (Agent Development Kit)** and maintains model-provider independence via centralized environment variables.

---

## 🏛️ Current Architecture & Control Flow

JobBud operates as a **master-orchestrated subagent system with a deterministic sequential pipeline runner** centered around `jobbud_agent`:

```text
                     User Input / Link / Portal Query
                                    │
                                    ▼
                     1. Obtención de Datos (Fetch API / Text)
                                    │
                                    ▼
                     2. Pre-Filtro Duro Inicial (Pre-LLM Python / 0 Tokens)
                        (title_blacklist, department_blacklist, location_filters)
                        - Registrar vacantes obtenidas en crudo (total_raw) y pre-descartadas
                        - Cargar vacantes conservadas en Caché Python (`LAST_FETCHED_JOBS_CACHE`)
                                    │
                                    ▼
                     3. Estructuración Híbrida en Memoria
                        - API Jobs: Diccionarios estructurados directos (0 LLM tokens)
                        - Raw Text / Links: `job_parser_agent` extrae rol, empresa y seniority con LLM
                                    │
                                    ▼
                     4. Filtro Determinista Post-Parseo & Capping (Python / 0 Tokens)
                        (blacklist_roles, blacklist_seniority, location_filters, max_jobs_per_board)
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
       [Falla Filtro / Cap Excedido]            [Pasa Filtro & Cap]
                │                                       │
       Descartar / Omitir                       5. Rankear en Lotes vía ADK `job_ranker_agent`
       (0 tokens de rankeo, 0 escrituras)          - Chunk size: k = min(5, ceil(R/4))
                                                   - Timer delay: delay_between_batches_seconds
                                                        │
                                                        ▼
                                                6. Guardar en jobs.json + Re-Evaluación & Re-Hidratación
                                                   - `save_ranked_jobs_batch` re-evalúa post-parseo si LLM
                                                     completó seniority/experiencia (descarte si falla).
                                                   - `run_job_processing_pipeline` re-hidrata objetos en memoria
                                                     con score, justificación, fortalezas y vacíos reales de jobs.json.
                                                        │
                                                        ▼
                                                Entregar Respuesta
```

---

### Subagent Responsibilities & Boundaries

- **`jobbud_agent` (Master Orchestrator)**:
  - Manages conversation, user intent, workflow execution, status changes, intermediate progress reporting, and final output formatting.
  - **Modo Ejecución Automática de Pipeline**: Al consultar un tablero de empleo (ej. Greenhouse), el orquestador ejecuta directamente `execute_job_pipeline_tool("todas")` para procesar el filtrado determinista y el rankeo en lotes de forma automática. Al finalizar, presenta de manera transparente el desglose exacto de vacantes obtenidas en crudo (Etapa 1), descartadas por filtro pre-parseo duro (Etapa 2), válidas post pre-parseo (Etapa 3), descartadas por filtro post-parseo (Etapa 4), omitidas por el tope configurado (`max_jobs_per_board`), evaluadas y rankeadas con LLM (Etapa 5) y guardadas en `jobs.json` (Etapa 6).

- **`job_parser_agent`**:
  - Parses raw unparsed job postings, normalizes data, detects language ("es"/"en"), extracts mandatory seniority ("Trainee", "Junior", "Semi-Senior", "Senior", "Lead / Executive"), stable IDs (`exactas_86_26`, `linkedin_4445031526`, `greenhouse_canonical_5569916`, `manual_<hash>`), and returns structured JSON.
  - **Boundary**: Never reads candidate profile or ranks jobs. Returns control back to `jobbud_agent` immediately.

- **`job_ranker_agent`**:
  - Reads `profile/candidate_profile.md` via `read_candidate_profile`, evaluates fit score (0–100) using LLM reasoning, updates `jobs.json` via `save_ranked_jobs_batch`, and generates detailed fit rationale.
  - **Boundary**: Exclusively handles fit scoring against the candidate profile.

- **`job_pipeline_runner` (`src/subagents/job_pipeline/runner.py`)**:
  - Executes the 6-stage deterministic pipeline in Python.
  - Reads configuration limits (`max_jobs_per_board`, `delay_between_batches_seconds`, `auto_pipeline_execution`) from [`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json).
  - Invokes `job_ranker_agent` natively via Google ADK `InMemoryRunner` for each batch chunk of size k = min(5, ceil(R / 4)), pausing `delay_between_batches_seconds` between chunks.
  - Re-hydrates in-memory job dictionaries from `jobs.json` post-ranking before returning results.

---

## 📐 Unified `jobs.json` Schema

All job sources (APIs, web fetchers, subagents, and manual entries) standardize job objects using a single unified JSON schema:
`id`, `created_at`, `title`, `company`, `location`, `work_mode`, `commitment`, `department`, `seniority`, `years_of_experience`, `salary_range`, `key_technologies`, `main_requirements`, `summary`, `raw_text`, `language`, `source_page`, `source_url`, `application_method`, `status` ("pending_ranking", "ranked", "disqualified", "applied"), `score`, `justification`, `strengths`, `gaps`, `ranked_at`, `user_notes`.

---

## 🚫 Dual Deterministic Filters (Zero Token Waste) & Post-Rank Re-evaluation

To drastically minimize LLM token consumption, the pipeline applies a multi-stage deterministic Python filtering process (0 tokens spent on discarded jobs):

```text
                  Aviso de Empleo / Portal API / Texto Crudo
                                     │
                                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │ ETAPA 1: Obtención de Datos en Crudo (API / Scraping)       │
      │ Registra total_raw (ej. 50 vacantes)                        │
      └──────────────────────────────┬──────────────────────────────┘
                                     │
                                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │ ETAPA 2: Filtros Duros Pre-Parseo (Pre-LLM en Python)       │
      │ 2.1 title_blacklist.md      -> Revisa título directo        │
      │ 2.2 department_blacklist.md -> Revisa metadatos de área     │
      │ 2.3 location_filters.json   -> Revisa país en metadatos    │
      └──────────────────────────────┬──────────────────────────────┘
                                     │
                             (Si supera Etapa 2)
                                     │
                                     ▼
                  3. Guardado en `jobs.json` + Ranker LLM
```

### Configuration Files (`profile/`)

| Archivo | Rol en el Filtrado / Pipeline | Regla / Propósito |
| :--- | :--- | :--- |
| **[`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json)** | **Controlador del Pipeline** | Configura `max_jobs_per_board` (cap máximo por consulta), `delay_between_batches_seconds` (timer entre lotes), `delay_between_boards_seconds` (timer entre tableros), `max_years_experience` (máximo de años de experiencia permitidos, ej: 3) y `auto_pipeline_execution`. |
| **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)** | **Filtro Duro Pre-Parseo** | Omite vacantes si el título contiene términos excluidos. |
| **[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)** | **Filtro Duro Pre-Parseo** | Omite si los metadatos de la API incluyen departamentos no deseados. |
| **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)** | **Filtro Post-Parseo** | Omite por área/rol parseado (ej. Sales, Recruiter, HR). |
| **[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)** | **Filtro Post-Parseo** | Omite si el seniority o los años requeridos (`years_of_experience > max_years_experience`) coinciden con niveles no deseados (ej. Senior, Lead). |
| **[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | **Pre y Post-Parseo** | Controla países permitidos (`allowed_countries`), ciudades/barrios permitidos para presencial/híbrido (`allowed_cities`), países bloqueados (`blocked_countries`), regiones remotas (`allowed_remote_regions`) y la flag **`allow_unspecified_location`**. |

---

## 🛠️ Modular Tools Structure (`src/tools/`)

All 19 core tools used by `jobbud_agent` are organized within the `src/tools/` package:

```text
src/tools/
├── __init__.py        # Re-exports HERRAMIENTAS_BASICAS (all 19 core tools)
├── fetchers.py        # External web scraping & portal fetching (fetch_exactas_job_board, fetch_linkedin_job_content, fetch_greenhouse_job_content)
├── queries.py         # Job querying, inspection & filters (check_existing_job, get_job_raw_text, get_job_details, get_top_job_recommendations, list_jobs_by_status, filter_jobs_by_blacklist, filter_job_by_location)
├── management.py      # Status edits, deletions, undo reversion & pipeline execution (mark_job_status, delete_job_from_json, revert_last_job_action, execute_job_pipeline_tool, execute_multi_board_pipeline_tool)
└── boards.py          # Job board registry & deterministic ordering (add_board_url, list_job_boards, get_board_to_analyze, delete_board_url)
```

---

## ⚙️ Configuration & Centralized Model Selection

- Centralized environment configuration is loaded via **[src/config.py](file:///home/santi/jobbud/src/config.py)** from `.env`.
- LLM model selection is controlled by a single environment variable:
  ```env
  DEFAULT_MODEL=gemini-3.1-flash-lite
  ```
- `jobbud_agent`, `job_parser_agent`, and `job_ranker_agent` all inherit `DEFAULT_MODEL`.

---

## 🆔 Standardized Platform ID Scheme & 3-Level Deduplication Strategy

To guarantee data integrity and eliminate duplicate job entries across sessions, JobBud enforces standardized platform IDs and a 3-level deduplication strategy:

### 1. Standardized Platform ID Format Scheme (`_generate_stable_job_id`)
* **Greenhouse**: `greenhouse_{board_token}_{job_id}` (e.g. `greenhouse_canonical_5569916`, `greenhouse_invgate_4495272002`). Extraído de metadatos API o de URLs tipo `job-boards.greenhouse.io/token/jobs/id`.
* **Exactas UBA**: `exactas_{num_part}` (e.g. `Oferta #86/26` → `exactas_86_26`). Extraído de metadatos o URLs tipo `/oferta/86-26`.
* **LinkedIn**: `linkedin_{numeric_id}` (extraído de metadatos o URLs tipo `view/4445031526`).
* **Ashby**: `ashby_{company}_{job_id}` (extraído de metadatos o URLs tipo `ashbyhq.com/company/id`).
* **Manual / Un-ID'd Text Fallback**: `manual_{md5(company:title)[:8]}` (e.g. `manual_bebce99c`). Si un aviso carece de ID al pasar por el ranker, se le asigna automáticamente un ID determinista según su URL o hash MD5.

### 2. 3-Level Deduplication Architecture
1. **Level 1 — Pre-Check Deduplication (`check_existing_job`)**:
   - Before parsing or ranking, checks `jobs.json` by ID, URL, or Title/Company string match.
   - If `AlreadyRanked`, halts processing immediately, saving 100% of LLM evaluation tokens.
2. **Level 2 — Insertion Deduplication (`save_multiple_jobs_json`)**:
   - Maintains an in-memory set of lowercase existing IDs (`existing_ids = {str(j.get("id")).lower() for j in jobs}`).
   - Skips saving any entry whose ID already exists in `jobs.json` (`skipped_count += 1`), preventing duplicate rows.
3. **Level 3 — Ranker Upsert & Immutability (`save_ranked_jobs_batch`)**:
   - Updates `score`, `justification`, `strengths`, `gaps`, `status: "ranked"`, and `ranked_at` in-place without duplicating the job entry.
   - **Ranker Immutability Rule**: Preserves all core source fields (`title`, `company`, `location`, `work_mode`, `commitment`, `raw_text`, `source_url`, `created_at`). Only populates `seniority` or `years_of_experience` if they were previously empty/undefined, and re-evaluates post-parse filters (`evaluate_post_parse_filters`).

### 3. Cascading Application Method & Direct Link Fallback (`_extract_application_method`)
To ensure every job has actionable application instructions, `_extract_application_method` applies a 4-level fallback:
1. **Direct Email in Text**: Detects contact email in body text $\rightarrow$ `Enviar CV por correo a...`.
2. **Explicit `source_url`**: Uses stored `source_url` $\rightarrow$ `Postulación web en: {source_url}`.
3. **HTTP/HTTPS URL in Body Text**: Scans raw description text for URLs $\rightarrow$ `Postulación web en: {url}`.
4. **Canonical URL Reconstruction**: Reconstructs direct web application links from Greenhouse (`job-boards.greenhouse.io`), LinkedIn (`linkedin.com/jobs/view`), Exactas, or registered portal URLs in `profile/board_urls.json`.

---

## 📝 Key Features & Lifecycles

1. **Deduplication & Pre-Check**:
   - Before parsing or ranking, `jobbud_agent` checks `check_existing_job`.
   - Prevents duplicate entries in `jobs.json` using stable IDs (e.g. `exactas_86_26`).

2. **User Status Management**:
   - Statuses: `"pending_ranking"`, `"ranked"`, `"disqualified"`, `"applied"`.
   - Users can mark jobs as descalificadas (`disqualified`) or aplicadas (`applied`), or delete positions.
   - Any status change or deletion prompt asks if the user wants to revert, and can be undone via `revert_last_job_action`.

3. **Top Recommendations**:
   - `get_top_job_recommendations(top_n)` lists top $N$ ranked jobs ordered by score, excluding `applied` and `disqualified` jobs by default.

4. **Raw Text Preservation**:
   - `raw_text` preserves full original unparsed job descriptions, retrievable via `get_job_raw_text`.

5. **Detailed Vacancy & Application Method Query (`get_job_details`)**:
   - Whenever the user asks for details or how to apply to a specific stored position, `get_job_details` retrieves all structured fields, fit rationale, strengths, gaps, and **mandatory direct application URL (`source_url`) and application instructions (`application_method`)**.

6. **Mandatory Board Re-listing**:
   - Whenever the user asks to see or list job boards (`list_job_boards`), `jobbud_agent` MUST ALWAYS re-execute `list_job_boards()` and output the full formatted numbered list verbatim, regardless of prior transcript history.

7. ⛔ **Prohibición Estricta de Datos Mock/Testing**:
   - JAMÁS se deben inventar, generar o guardar vacantes de prueba (ej. `test_adk_rank_1`, `test_job_1`, `sample_job`) en `jobs.json`, ni siquiera para pruebas, demostraciones o debugging. Únicamente vacantes reales procesadas desde APIs o ingresadas explícitamente por el usuario pueden ser guardadas en `jobs.json`.

---

## 📐 Development Directives

1. Maintain strict separation of concerns: Parsing $\rightarrow$ `job_parser_agent`, Ranking $\rightarrow$ `job_ranker_agent`, Flow Control $\rightarrow$ `jobbud_agent`.
2. Ensure subagents return control to `jobbud_agent` after each action.
3. Keep tool implementations inside `src/tools/` organized by domain (`fetchers.py`, `queries.py`, `management.py`, `boards.py`).
4. Preserve model-agnostic flexibility via `src/config.py`.
5. ⛔ **NO MOCK DATA IN JOBS.JSON**: Never inject artificial or test job entries into `jobs.json`. Only real job postings are persisted.
