# 💼 JobBud — Intelligent Job Search Assistant with Google ADK

[![English](https://img.shields.io/badge/Language-English-red.svg)](README.md) [![Spanish](https://img.shields.io/badge/Language-Español-blue.svg)](README.es.md) [![Live Run Output Example](https://img.shields.io/badge/Live_Example-View_Report-green.svg)](EXAMPLE_OUTPUT.md)

> 📊 **[Click here to view a real multi-board processing output example (29 boards analyzed)](EXAMPLE_OUTPUT.md)**

**JobBud** is a conversational agent and master orchestrator designed to automate job searching, filtering, evaluation, and application lifecycle management for Computer Science students and Software Engineers.

The system ingests job postings from multiple sources (Greenhouse portal APIs, Exactas UBA web scraping, LinkedIn links, or raw text), applies a **two-stage deterministic Python filtering process (0 tokens)**, evaluates fit match (*score 0–100*) against a candidate profile (`profile/candidate_profile.md`) using batch LLM subagents, and manages the full application lifecycle in `jobs.json`.

---

## 🏛️ System Architecture (6 Master Stages)

```text
                     User Input / Link / Portal Query
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 1. Unified Ingestion Layer (`src/fetchers/`)                │
       │ - greenhouse.py: API -> List[JobDict] (0 LLM tokens)        │
       │ - ashby.py: API -> List[JobDict] (0 LLM tokens)             │
       │ - exactas.py: Scrapes UBA -> calls job_parser_agent         │
       │ - linkedin.py: Fetches HTML -> calls job_parser_agent       │
       │ - manual.py: Ingests raw text -> calls job_parser_agent     │
       │ -> Output Contract: Standardized List[JobDict]              │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 2. Pre-Filtro Duro Inicial (Pre-LLM Python / 0 Tokens)      │
       │ (title_blacklist, department_blacklist, location_filters)   │
       │ - Record raw positions (total_raw) and discarded count      │
       │ - Cache retained jobs in memory (`LAST_FETCHED_JOBS_CACHE`) │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 3. In-Memory Structured Normalization                       │
       │ - Confirms normalized JobDicts in memory with stable IDs    │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 4. Post-Parse Filter, Invariant Dedupe & Board Cap          │
       │ (blacklist_roles, blacklist_seniority, location, max_years) │
       │ - Post-Parse: Discards forbidden roles & seniority levels.  │
       │ - Semantic YOE Filter: Drops if numeric YOE > max_years.    │
       │ - Dedupe: Skips jobs already in jobs.json (0 LLM tokens).   │
       │ - Optional Cap: max_jobs_per_board limits new positions.    │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
       [Filter Fail / In jobs.json / Capped]     [New Vacancy & Passes Filters]
                │                                       │
       Discard / Skip                           5. Batch Ranking via ADK `job_ranker_agent`
       (0 ranking tokens, 0 writes)                - Sets `set_ranking_batch_cache(chunk)`
                                                   - Chunk size: k = min(5, ceil(R/4))
                                                   - Delay between batches: delay_between_batches_seconds
                                                   - Clears `clear_ranking_batch_cache()` in `finally`
                                                        │
                                                        ▼
                                                6. Deterministic Merge & Save to jobs.json
                                                   - `save_ranked_jobs_batch` merges memory JobDict
                                                     with ranker evaluation (score, justification, strengths, gaps).
                                                   - Validates ID belongs to active batch and is new.
                                                   - Persists complete record to `jobs.json`.
                                                        │
                                                        ▼
                                                Deliver Markdown Report
```

---

## ✨ Key Features

1. **Unified Ingestion Layer (`src/fetchers/`)**:
   - Encapsulates portal-specific logic into dedicated modules (`greenhouse.py`, `ashby.py`, `exactas.py`, `linkedin.py`, `manual.py`).
   - Every fetcher enforces a standardized output contract returning a `List[JobDict]`, ensuring all downstream stages receive clean, uniform data.
   - Fetchers are the **sole callers** of `job_parser_agent`.

2. **Dual Deterministic Filters & Zero Token Waste**:
   - **Stage 2 Pre-Parse Filter**: Discards unapproved job titles, departments, or non-target locations directly from raw API metadata with **0 LLM tokens**.
   - **Stage 4 Post-Parse Filter**: Discards incompatible seniority (`Senior`, `Lead`), excluded roles (`Sales`, `Recruiter`), and positions exceeding `max_years_experience` in Python before ranking.

3. **Semantic Experience & Seniority Extraction (No Regex False Positives)**:
   - Years of required experience (`years_of_experience`) and seniority level are extracted semantically by `job_parser_agent` using natural language understanding, eliminating fragile regex heuristics that confuse company history/tenure with job requirements.
   - The Stage 4 filter only drops positions when an explicit numeric value exceeds `max_years_experience`.

4. **Modular Sequential Pipeline Architecture (`src/subagents/job_pipeline/`)**:
   - Decomposed into single-responsibility submodules: `single_pipeline.py`, `multi_pipeline.py`, `adk_clients.py`, `config.py`, `state.py`, `scope_parser.py`, and `reporter.py`.
   - Propagates 8 explicit telemetry metrics across all runs: `total_raw`, `pre_discarded_count`, `post_discarded_count`, `deduped_count`, `capped_count`, `sent_to_ranker_count`, `successfully_ranked_count`, and `ranking_errors_count`.

5. **Automated Pipeline Execution & Batch Throttling**:
   - Automatically executes filtering and batch ranking without requiring chat confirmation pauses.
   - `max_jobs_per_board` in `profile/pipeline_config.json` limits maximum positions per query.
   - `delay_between_batches_seconds` and `delay_between_boards_seconds` enforce configurable pauses to prevent API rate limits (`429`).

6. **Standardized Platform IDs & Invariant Deduplication**:
   - **Canonical ID Scheme**: Deterministic IDs (`greenhouse_{board}_{id}`, `ashby_{company}_{id}`, `exactas_{num}`, `linkedin_{id}`, and MD5 hashes `manual_{md5(company:title)[:8]}`).
   - **Invariant Deduplication**: Existing positions in `jobs.json` are skipped automatically before ranking slots are consumed.

7. **Extensive Vacancy Inspection & Cascading Direct Application Links (`get_job_details`)**:
   - Retrieves full structured job data, fit rationale, strengths, gaps, and **direct application URLs (`source_url`) and application instructions (`application_method`)** using a robust 4-level fallback.

8. **Multi-Language Support & Dynamic Internationalization**:
   - Configured via `profile/pipeline_config.json` (`"language": "es" | "en" | null`).
   - If language is unspecified or invalid, `jobbud_agent` proactively prompts the user and persists the choice using `set_language_preference`.
   - Generates transparent pipeline reports in the configured language via `src/subagents/job_pipeline/reporter.py`.
   - Invariant: `job_parser_agent` remains publication-centric, while `job_ranker_agent` evaluates and returns rationale in the user's preferred language.

9. **Strict JSON Schema Contract for `strengths` and `gaps`**:
   - `strengths` and `gaps` are guaranteed to be flat `List[str]` (`["string 1", "string 2"]`).
   - Deterministic normalization (`_normalize_string_list`) ensures all entries in `jobs.json` remain uniform without nested objects.

10. ⛔ **Zero Mock Data Policy**:
    - Strict prohibition against creating or persisting synthetic or test jobs (`test_adk_rank_1`) in `jobs.json`.

---

## 📂 Project Structure

```text
jobbud/
├── main.py                      # Main interactive CLI entrypoint (InMemoryRunner)
├── jobs.json                    # Central database in unified JSON schema
├── README.md                    # Project documentation (English)
├── README.es.md                 # Project documentation (Spanish)
├── GEMINI.md                    # Architecture specification & agent directives
├── profile/                     # Candidate profile & deterministic filtering rules
│   ├── candidate_profile.md     # Candidate background, skills & goals
│   ├── ranking_policy.md        # User rule hierarchy, scoring policy & visibility directives
│   ├── pipeline_config.json     # Pipeline limits (language, board cap, batch timer, max years exp, auto flag)
│   ├── board_urls.json          # Persistent job board registry
│   ├── location_filters.json    # Allowed/blocked countries, cities, and remote rules
│   ├── title_blacklist.md       # Pre-Parse title blacklist
│   ├── department_blacklist.md  # Pre-Parse API department blacklist
│   ├── blacklist_roles.md       # Post-Parse role/area blacklist
│   └── blacklist_seniority.md   # Post-Parse seniority blacklist
└── src/
    ├── agent.py                 # Main `jobbud_agent` instance (Google ADK Agent with 22 tools, 0 subagents)
    ├── config.py                # Environment variable loader (.env)
    ├── guidelines.md            # System prompt & conversational guidelines
    ├── fetchers/                # Unified Ingestion Layer returning List[JobDict]
    │   ├── __init__.py          # Exposes fetcher functions and agent tools
    │   ├── base.py              # Text compression & technology extractor
    │   ├── greenhouse.py        # Greenhouse REST API connector (0 LLM tokens)
    │   ├── ashby.py             # Ashby Public API connector (0 LLM tokens)
    │   ├── exactas.py           # Exactas UBA CS scraper + parser integration
    │   ├── linkedin.py          # LinkedIn job extractor + parser integration
    │   └── manual.py            # Raw text normalizer + parser integration
    ├── subagents/
    │   ├── job_parser/          # Job parsing & structuring subagent (programmatic worker)
    │   │   ├── job_parser.py    # ADK Agent definition
    │   │   ├── guidelines.md    # Extraction schema guidelines (incl. commitment & YOE)
    │   │   └── tools.py         # ID generator, application method & unified JobDict builder
    │   ├── job_ranker/          # Fit match evaluation & scoring subagent (batch worker)
    │   │   ├── job_ranker.py    # ADK Agent definition
    │   │   ├── guidelines.md    # Ranking criteria & guidelines
    │   │   └── tools.py         # Evaluation tools, profile & policy readers, batch persistence
    │   └── job_pipeline/        # Modular deterministic sequential pipeline
    │       ├── __init__.py      # Re-exports pipeline entrypoints
    │       ├── runner.py        # Backward-compatible facade
    │       ├── single_pipeline.py # 6-stage sequential single board/selection runner
    │       ├── multi_pipeline.py  # Multi-board orchestrator & timer delays
    │       ├── adk_clients.py   # ADK InMemoryRunner bridge & 429 quota backoff
    │       ├── config.py        # Pipeline config parser
    │       ├── state.py         # Cache & selection parser
    │       ├── scope_parser.py  # Scope, relative time & index filtering
    │       └── reporter.py      # Telemetry & multi-board report formatter (i18n)
    └── tools/                   # Modular collection of 22 core tools
        ├── __init__.py          # Re-exports HERRAMIENTAS_BASICAS (all 22 core tools)
        ├── queries.py           # Job querying, inspection & deterministic filters
        ├── management.py        # Status edits, deletions, language prefs, undo & pipeline tools
        └── boards.py            # Job board registry management & ordering
```

---

## 👤 How to Adapt JobBud to Your Candidate Profile (`profile/`)

> **JobBud’s core architecture is 100% generic.** You **NEVER** need to edit Python source code (`src/`), agent guidelines (`guidelines.md`), or pipeline logic to adapt JobBud to a new candidate.
> 
> **To adapt JobBud to your own profile, you only modify the files inside the [`profile/`](file:///home/santi/jobbud/profile/) folder.**

The diagram below illustrates how each file in `profile/` alters the 6-stage pipeline:

```text
Job Boards (profile/board_urls.json)
        │
        ▼  [Stage 1: Fetching]
Title & Department Blacklists (title_blacklist.md, department_blacklist.md, location_filters.json)
        │
        ▼  [Stage 2: Pre-Parse Hard Filter (0 Tokens)]
Job Parser Subagent
        │
        ▼  [Stage 3: LLM Parsing & Structuring]
Role, Seniority & Experience Limits (blacklist_roles.md, blacklist_seniority.md, pipeline_config.json)
        │
        ▼  [Stage 4: Post-Parse Hard Filter (0 Tokens)]
Candidate Profile & Ranking Policy (candidate_profile.md, ranking_policy.md)
        │
        ▼  [Stage 5: LLM Ranking & Fit Evaluation (0-100 Score)]
Evaluated Jobs Saved to jobs.json
```

### Breakdown by Pipeline Stage:

| Pipeline Stage | `profile/` File(s) Used | How It Alters the Pipeline Process |
| :--- | :--- | :--- |
| **Stage 1 (Data Acquisition)** | **[`profile/board_urls.json`](file:///home/santi/jobbud/profile/board_urls.json)** | Specifies the target job board URLs (Greenhouse, Ashby, LinkedIn, etc.) that JobBud fetches postings from. |
| **Stage 2 (Pre-Parse Filter)** | **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)**<br>**[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)**<br>**[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | Deterministic Python filter matching raw titles, API department metadata, and location rules. Rejects non-target jobs early with **0 LLM token cost**. |
| **Stage 4 (Post-Parse Filter)** | **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)**<br>**[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)**<br>**[`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json)** | Deterministic Python filter matching extracted fields. Rejects forbidden roles, incompatible seniorities, or jobs exceeding `max_years_experience`. |
| **Stage 5 (LLM Ranking)** | **[`profile/candidate_profile.md`](file:///home/santi/jobbud/profile/candidate_profile.md)**<br>**[`profile/ranking_policy.md`](file:///home/santi/jobbud/profile/ranking_policy.md)** | `job_ranker_agent` reads **candidate background** and **candidate scoring directives** dynamically to calculate exact fit score (0-100), justification, strengths, and gaps. |

---

## ⚙️ Profile Configuration & Filters (`profile/`)

All candidate configuration and filtering rules are located in the [`profile/`](file:///home/santi/jobbud/profile/) directory:

| File | Role / Type | Pipeline Stage | Description & Filtering Rules |
| :--- | :--- | :--- | :--- |
| **[`profile/candidate_profile.md`](file:///home/santi/jobbud/profile/candidate_profile.md)** | Professional Profile | **Stage 5 (LLM Ranking)** | Defines academic background (CS Student UBA), tech stack (Python, C++, SQL), English level (C2), and preferences. Used by `job_ranker_agent` to compute fit match score (0-100). |
| **[`profile/ranking_policy.md`](file:///home/santi/jobbud/profile/ranking_policy.md)** | User Ranking Policy | **Stage 5 (LLM Ranking)** | Defines user-selected rule hierarchy (Level 1-8), scoring vs recall separation policy, decision questions, and strengths/gaps formatting rules. |
| **[`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json)** | Pipeline Configuration | **Stages 4 & 5 (Pipeline Rules)** | Configures `max_jobs_per_board` (max jobs to rank per query), `delay_between_batches_seconds` (batch LLM timer), `delay_between_boards_seconds` (inter-board timer), `max_years_experience` (max allowed required experience years, e.g. 3), and `auto_pipeline_execution`. |
| **[`profile/board_urls.json`](file:///home/santi/jobbud/profile/board_urls.json)** | Job Board Registry | **Stage 1 (Data Acquisition)** | Persistent JSON store of registered job board URLs (Greenhouse, Ashby, etc.) and analysis timestamps. Managed deterministically by `src/tools/boards.py`. |
| **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)** | **Pre-Parse Hard Filter** | **Stage 2 (Python / 0 Tokens)** | Blacklist terms matched against the raw job title. Omits non-target jobs like *Sales, Recruiter, HR, Director, Chief, Manager* before parsing. |
| **[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)** | **Pre-Parse Hard Filter** | **Stage 2 (Python / 0 Tokens)** | Blacklist terms matched against API department metadata. Omits non-technical areas (e.g. *Customer Service, Marketing, Finance*). |
| **[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | **Location & Country Filter** | **Stages 2 & 4 (Python / 0 Tokens)** | Specifies allowed countries (`allowed_countries`: `["Argentina"]`), allowed cities/neighborhoods for on-site/hybrid (`allowed_cities`), blocked countries (`blocked_countries`), remote regions, and `allow_unspecified_location` rule. |
| **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)** | **Post-Parse Filter** | **Stage 4 (Python / 0 Tokens)** | Blacklist terms matched against structured role/area fields (e.g. *Human Resources, Sales Representative, Commercial, UX/UI Design*). |
| **[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)** | **Post-Parse Filter** | **Stage 4 (Python / 0 Tokens)** | Blacklist terms matched against structured seniority levels and required experience years (`years_of_experience > max_years_experience`). Discards jobs assigned to *Senior, Lead, Staff, Principal, Director, Manager*. |

---

## 🛠️ Core Tools (`HERRAMIENTAS_BASICAS`)

`jobbud_agent` is equipped with **20 modular tools**:

| Tool | Domain | Purpose |
| :--- | :--- | :--- |
| `check_existing_job` | Queries | Checks deduplication by ID or URL in `jobs.json`. |
| `get_job_raw_text` | Queries | Retrieves full raw unparsed job description. |
| `get_job_details` | Queries | Returns full structured job report with direct application link. |
| `get_top_job_recommendations` | Queries | Lists top N job offers ordered by fit score descending. |
| `list_jobs_by_status` | Queries | Lists jobs filtered by status (`ranked`, `applied`, `disqualified`). |
| `filter_jobs_by_blacklist` | Queries | Evaluates match against blacklists. |
| `filter_job_by_location` | Queries | Filters by country and work mode. |
| `mark_job_status` | Management | Updates position status in `jobs.json`. |
| `delete_job_from_json` | Management | Removes a job entry from `jobs.json`. |
| `revert_last_job_action` | Management | Undoes the last status change or deletion. |
| `execute_job_pipeline_tool` | Management | Runs the deterministic sequential filtering and batch ranking runner for single job lists. |
| `execute_multi_board_pipeline_tool` | Management | Runs the automated multi-board sequential pipeline with inter-board timers and Top 5 report. |
| `fetch_linkedin_job_content` | Fetchers | Extracts content from LinkedIn job posts. |
| `fetch_exactas_job_board` | Fetchers | Fetches job postings from Exactas UBA job board. |
| `fetch_greenhouse_job_content` | Fetchers | Fetches job listings via Greenhouse portal API. |
| `fetch_ashby_job_content` | Fetchers | Fetches job listings via Ashby Public API. |
| `add_board_url` | Boards | Registers a new job board URL in `profile/board_urls.json`. |
| `list_job_boards` | Boards | Lists registered job boards sorted oldest to newest. |
| `get_board_to_analyze` | Boards | Resolves and fetches a job board by index number or name. |
| `delete_board_url` | Boards | Removes a registered job board. |

---

## 🚀 Installation & Setup

### 1. Prerequisites & Installation

```bash
git clone https://github.com/user/jobbud.git
cd jobbud

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables Setup

Create or edit `.env` in the project root:

```env
GOOGLE_API_KEY=your_google_gemini_api_key
DEFAULT_MODEL=gemini-3.1-flash-lite
ADK_DEFAULT_APP_NAME=src
```

### 3. Execution

#### Option A: Interactive Command Line Interface (CLI)

```bash
python main.py
```

#### Option B: Google ADK Web Interface

```bash
adk web src
```

---

## 💬 Sample Conversational Commands

- **List Registered Job Boards**:
  > *"mis boards"* or *"listar tableros"*
- **Analyze a Job Board**:
  > *"analizá el board 1"* or *"analizar board InvGate"*
- **Confirm Position Selection**:
  > *"evaluá la 1 y la 3"* or *"todas"*
- **View Full Details & Application Method**:
  > *"dame información sobre la vacante greenhouse_invgate_4495272002"*
- **Get Top Recommendations**:
  > *"mostrame el top 5 para postularme"*
- **Mark Job as Applied / Disqualified**:
  > *"marcar la vacante X como aplicada"*
- **Revert Last Action**:
  > *"deshacer"*
