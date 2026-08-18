# 💼 JobBud — Intelligent Job Search Assistant with Google ADK

[![English](https://img.shields.io/badge/Language-English-red.svg)](README.md) [![Spanish](https://img.shields.io/badge/Language-Español-blue.svg)](README.es.md) [![Live Run Output Example](https://img.shields.io/badge/Live_Example-View_Report-green.svg)](EXAMPLE_OUTPUT.md) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

> 📊 **[Click here to view a real multi-board processing output example (29 boards analyzed)](EXAMPLE_OUTPUT.md)**

**JobBud** is a conversational agent and master orchestrator designed to automate job searching, filtering, evaluation, and application lifecycle management for technical professionals and students.

The system ingests job postings from multiple sources (Greenhouse, Ashby, Lever portal APIs, Exactas UBA web scraping, LinkedIn links, or raw text), applies a **two-stage deterministic Python filtering process (0 tokens)**, evaluates fit match (*score 0–100*) against a candidate profile (`profile/candidate_profile.md`) using batch LLM subagents, and manages the full application lifecycle in `jobs.json`.

---

## 📑 Table of Contents

1. [🏛️ System Architecture (6 Master Stages)](#️-system-architecture-6-master-stages)
2. [✨ Key Features](#-key-features)
3. [📂 Project Structure](#-project-structure)
4. [📐 Unified Data Schema (`JobDict`)](#-unified-data-schema-jobdict)
   - 4.1. [Field and Type Specification](#41-field-and-type-specification)
   - 4.2. [Contract for Strengths, Gaps, and Statuses](#42-contract-for-strengths-gaps-and-statuses)
   - 4.3. [Platform Stable ID Scheme](#43-platform-stable-id-scheme)
5. [👤 Step-by-Step Profile Configuration Guide (`profile/`)](#-step-by-step-profile-configuration-guide-profile)
   - 5.1. [Step 1: Your Candidate Profile (`candidate_profile.md`)](#51-step-1-your-candidate-profile-candidate_profilemd)
   - 5.2. [Step 2: Ranking Rules & Policy (`ranking_policy.md`)](#52-step-2-ranking-rules--policy-ranking_policymd)
   - 5.3. [Step 3: Engine Pipeline Parameters (`pipeline_config.json`)](#53-step-3-engine-pipeline-parameters-pipeline_configjson)
   - 5.4. [Step 4: Location & Work Mode Filters (`location_filters.json`)](#54-step-4-location--work-mode-filters-location_filtersjson)
   - 5.5. [Step 5: Pre & Post-Parse Blacklists (`*.md`)](#55-step-5-pre--post-parse-blacklists-md)
   - 5.6. [Step 6: Board URL Registry (`board_urls.json`)](#56-step-6-board-url-registry-board_urlsjson)
6. [🛠️ Modular Tool Suite (`HERRAMIENTAS_BASICAS`)](#️-modular-tool-suite-herramientas_basicas)
7. [🚀 Installation & Setup](#-installation--setup)
   - 7.1. [Prerequisites & Installation](#71-prerequisites--installation)
   - 7.2. [Environment Configuration (`.env`)](#72-environment-configuration-env)
   - 7.3. [Running JobBud (CLI vs Web ADK)](#73-running-jobbud-cli-vs-web-adk)
8. [💬 Example Conversational Commands](#-example-conversational-commands)
9. [🛡️ Data Integrity & Persistence](#️-data-integrity--persistence)

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
       │ - lever.py: API -> List[JobDict] (0 LLM tokens)             │
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
                                                6. Deterministic Merge & Persistence in jobs.json
                                                   - `save_ranked_jobs_batch` merges in-memory JobDict
                                                     with ranker evaluation (score, rationale, etc.).
                                                   - Validates ID belongs to active batch and is new.
                                                   - Persists complete record into `jobs.json`.
                                                        │
                                                        ▼
                                                Deliver Markdown Telemetry Report
```

---

## ✨ Key Features

1. **Unified Ingestion Layer (`src/fetchers/`)**:
   - Encapsulates portal-specific logic in dedicated modules (`greenhouse.py`, `ashby.py`, `lever.py`, `exactas.py`, `linkedin.py`, `manual.py`).
   - Every fetcher strictly adheres to the Greenhouse-standard `List[JobDict]` return contract.
   - Structured API fetchers (Greenhouse, Ashby, Lever) consume **0 LLM tokens** during ingestion. Unstructured sources (Exactas, LinkedIn, Manual text) are the **sole callers** of `job_parser_agent`.

2. **Dual Deterministic Python Filters (Zero Token Waste)**:
   - **Stage 2 (Pre-Parse)**: Drops non-matching titles, departments, or forbidden locations from raw metadata with **0 LLM tokens**.
   - **Stage 4 (Post-Parse)**: Drops unwanted roles, seniorities, and positions exceeding `max_years_experience` in Python prior to LLM evaluation.

3. **Semantic Extraction for Seniority and Experience (No Fragile Regex)**:
   - Required years of experience (`years_of_experience`) and seniority level are semantically extracted by `job_parser_agent`, avoiding regular expression errors.
   - Stage 4 filter drops jobs only when an explicit numeric value exceeds `max_years_experience`.

4. **Modular Sequential Pipeline Architecture (`src/subagents/job_pipeline/`)**:
   - Single-responsibility modules: `single_pipeline.py`, `multi_pipeline.py`, `adk_clients.py`, `config.py`, `state.py`, `scope_parser.py`, and `reporter.py`.
   - Real-time telemetry tracking 8 metrics: raw vacancies, pre-discarded, valid candidates, post-discarded, deduplicated, capped, sent to ranker, and successfully saved.

5. **Automated Batch Execution & Rate-Limit Protection**:
   - Autonomous execution without manual prompts when querying boards.
   - Configurable limits (`max_jobs_per_board`) and inter-batch/inter-board timers prevent API quota exhaustion (`HTTP 429`).

6. **Canonical Stable IDs & Invariant Deduplication**:
   - **Stable ID Scheme**: IDs formatted by platform (`greenhouse_{board}_{id}`, `ashby_{company}_{id}`, `lever_{company}_{id}`, `exactas_{num}`, `linkedin_{id}`, and MD5 hashes `manual_{hash}`).
   - **Invariant Deduplication**: Jobs already existing in `jobs.json` are skipped automatically before spending evaluation tokens.

7. **Detailed Vacancy & Application Method Queries (`get_job_details`)**:
   - Retrieves complete records, fit justification, strengths, gaps, and **direct canonical application URLs (`source_url`) with actionable instructions (`application_method`)** resolved via a 4-level fallback.

8. **Dynamic Internationalization & Multi-Language Support**:
   - Configurable in `profile/pipeline_config.json` (`"language": "es" | "en" | null`).
   - Generates telemetry and fit justifications in the user's chosen language.

---

## 📂 Project Structure

```text
jobbud/
├── main.py                      # Interactive CLI entry point (InMemoryRunner)
├── jobs.json                    # Central database in unified JSON format
├── README.md                    # Project documentation (English)
├── README.es.md                 # Project documentation (Spanish)
├── GEMINI.md                    # Agent architecture and system specifications
├── profile/                     # Candidate profile and configurable rules
│   ├── candidate_profile.md     # Professional background, skills, and preferences
│   ├── ranking_policy.md        # User-defined scoring hierarchy, rubric, and rules
│   ├── pipeline_config.json     # Pipeline limits (language, cap, timers, max YOE)
│   ├── board_urls.json          # Persistent registry of target job boards
│   ├── location_filters.json    # Allowed countries, cities, and remote rules
│   ├── title_blacklist.md       # Excluded title terms (Pre-Parse)
│   ├── department_blacklist.md  # Excluded department metadata (Pre-Parse)
│   ├── blacklist_roles.md       # Excluded parsed roles (Post-Parse)
│   └── blacklist_seniority.md   # Excluded seniority levels (Post-Parse)
└── src/
    ├── agent.py                 # Main `jobbud_agent` instance (ADK Agent with 23 tools)
    ├── config.py                # Centralized environment variable loader (.env)
    ├── guidelines.md            # System prompts and conversational directives
    ├── fetchers/                # Unified Ingestion Layer returning List[JobDict]
    │   ├── __init__.py          # Exported fetcher functions and agent tools
    │   ├── base.py              # Technology extractor and text utilities
    │   ├── greenhouse.py        # Greenhouse REST API connector (0 LLM tokens)
    │   ├── ashby.py             # Ashby HQ Public API connector (0 LLM tokens)
    │   ├── lever.py             # Lever Public API connector (0 LLM tokens)
    │   ├── exactas.py           # FCEyN UBA scraper + parser integration
    │   ├── linkedin.py          # LinkedIn job posting extractor + parser
    │   └── manual.py            # Raw text normalizer + parser
    ├── subagents/
    │   ├── job_parser/          # Extraction subagent (programmatic worker)
    │   │   ├── job_parser.py    # ADK Agent definition
    │   │   ├── guidelines.md    # Extraction schema and normalization rules
    │   │   └── tools.py         # ID generator, application method & JobDict builder
    │   ├── job_ranker/          # Fit evaluation subagent (batch worker)
    │   │   ├── job_ranker.py    # ADK Agent definition
    │   │   ├── guidelines.md    # Fit scoring criteria and rules
    │   │   └── tools.py         # Profile readers and batch JSON persistence
    │   └── job_pipeline/        # Modular deterministic sequential pipeline
    │       ├── __init__.py      # Re-exports pipeline entry points
    │       ├── runner.py        # Backward-compatibility facade
    │       ├── single_pipeline.py # 6-stage sequential runner for boards/selections
    │       ├── multi_pipeline.py  # Multi-board orchestrator with timers
    │       ├── adk_clients.py   # ADK InMemoryRunner bridge & 429 backoff
    │       ├── config.py        # Pipeline configuration reader
    │       ├── state.py         # In-memory cache & index selector
    │       ├── scope_parser.py  # Scope, relative date & index parser
    │       └── reporter.py      # Telemetry & Markdown report formatter (i18n)
    └── tools/                   # Modular suite of 23 tools
        ├── __init__.py          # Exports HERRAMIENTAS_BASICAS (all 23 tools)
        ├── queries.py           # Inspections, lookups, and deterministic filters
        ├── management.py        # Status edits, deletions, language, undo & pipeline tools
        └── boards.py            # Board registry and deterministic ordering
```

---

## 📐 Unified Data Schema (`JobDict`)

Every job vacancy processed in JobBud is standardized into a unified **26-field** dictionary (`JobDict`) before evaluation and persistence in `jobs.json`.

### 4.1. Field and Type Specification

| Field | Type | Nullable? | Description and Allowed Values |
| :--- | :---: | :---: | :--- |
| `id` | `str` | No | Deterministic unique identifier (e.g. `greenhouse_invgate_4495272002`, `exactas_86_26`). |
| `created_at` | `str` | No | ISO timestamp when ingested into the system (e.g. `2026-08-18T06:48:54.728087`). |
| `title` | `str` | No | Clean, normalized job title. |
| `company` | `str` | No | Hiring company or organization name. |
| `location` | `str` | No | Normalized location string (e.g. `Buenos Aires, Argentina`, `Remote - US`). |
| `work_mode` | `str` | No | Work modality: `"Remoto"`, `"Híbrido"`, `"Presencial"`, or `"Not specified"`. |
| `commitment` | `str` | No | Work commitment: `"Full-time"`, `"Part-time"`, `"Contract"`, `"Internship"`, or `"Not specified"`. |
| `department` | `str` | No | Functional area or department (e.g. `Engineering`, `Data`, `QA`, `Sales`). |
| `seniority` | `str` | No | Experience level: `"Trainee"`, `"Junior"`, `"Semi-Senior"`, `"Senior"`, `"Lead / Executive"`. |
| `years_of_experience` | `int` | **Yes** | Explicit minimum years required (numeric integer or `null` if unspecified). |
| `salary_range` | `str` | **Yes** | Published salary or compensation range, or `null`. |
| `key_technologies` | `List[str]` | No | Flat array of required tools, frameworks, and technologies. |
| `main_requirements` | `List[str]` | No | Flat array of key candidate qualifications and requirements. |
| `summary` | `str` | No | Concise 2-3 sentence overview of the role and responsibilities. |
| `raw_text` | `str` | No | Full, unedited raw job description text preserved verbatim. |
| `language` | `str` | No | Detected original language code (`"es"` or `"en"`). |
| `source_page` | `str` | No | Source platform name (e.g. `Greenhouse`, `Ashby`, `Lever`, `Exactas UBA`, `LinkedIn`). |
| `source_url` | `str` | No | Direct canonical URL to the job posting. |
| `application_method` | `str` | No | Actionable application instructions (direct application link or contact email). |
| `status` | `str` | No | Lifecycle status: `"new"`, `"pending_ranking"`, `"ranked"`, `"disqualified"`, `"applied"`. |
| `score` | `int` | **Yes** | Fit score from 0 to 100 evaluated by the ranker against profile (`null` if unranked). |
| `justification` | `str` | **Yes** | Concise rationale explaining the awarded score written by the ranker LLM. |
| `strengths` | `List[str]` | No | Flat array of candidate matching points and advantages. |
| `gaps` | `List[str]` | No | Flat array of missing skills, gaps, or potential concerns. |
| `ranked_at` | `str` | **Yes** | ISO timestamp when evaluated by `job_ranker_agent`, or `null`. |
| `user_notes` | `str` | **Yes** | Custom user remarks and notes, or `null`. |

### 4.2. Contract for Strengths, Gaps, and Statuses

* **Strict Array Contract for `strengths` and `gaps`**:
  ```json
  "strengths": ["string", "string"],
  "gaps": ["string", "string"]
  ```
  Storing nested objects or dicts (e.g. `[{"text": "..."}]`) is strictly prohibited. Runtime normalization (`_normalize_string_list`) guarantees that entries in `jobs.json` are always flat `List[str]`.

* **Valid Lifecycle Statuses (`status`)**:
  - `"new"`: Newly fetched vacancy held in memory.
  - `"pending_ranking"`: Stored in `jobs.json` without LLM fit evaluation.
  - `"ranked"`: Evaluated with score (0–100), rationale, strengths, and gaps.
  - `"applied"`: Position the user has already applied to.
  - `"disqualified"`: Manually dismissed vacancy.

### 4.3. Platform Stable ID Scheme

* **Greenhouse**: `greenhouse_{board_token}_{job_id}` (e.g. `greenhouse_invgate_4495272002`).
* **Ashby HQ**: `ashby_{company}_{job_id}` (e.g. `ashby_cursor_123456`).
* **Lever**: `lever_{company}_{job_id}` (e.g. `lever_ryzlabs_abcd-1234`).
* **Exactas UBA**: `exactas_{num_part}` (e.g. `exactas_86_26`).
* **LinkedIn**: `linkedin_{numeric_id}` (e.g. `linkedin_4445031526`).
* **Manual Text**: `manual_{md5(company:title)[:8]}` (e.g. `manual_bebce99c`).

---

## 👤 Step-by-Step Profile Configuration Guide (`profile/`)

> **JobBud is 100% profile-agnostic.** You **NEVER** need to edit Python source code (`src/`) or agent prompts (`guidelines.md`).
> 
> **To adapt JobBud to your own background and career, customize only the files in the [`profile/`](profile/) folder.**

### 5.1. Step 1: Your Candidate Profile (`candidate_profile.md`)
* **Path**: [`profile/candidate_profile.md`](profile/candidate_profile.md)
* **Format**: Markdown (`.md`)
* **Purpose**: Read by `job_ranker_agent` to evaluate fit against each posting.
* **Recommended Template**:
  ```markdown
  # Candidate Professional Profile

  ## 🎓 Education
  - **Degree**: B.S. in Computer Science / Software Engineering
  - **Institution**: University of Buenos Aires (UBA)
  - **Current Status**: Senior student (80% completed)

  ## 💼 Work Experience
  - **Junior Developer** at Company X (2024 - Present):
    - Built backend REST APIs in Python (FastAPI) and PostgreSQL databases.
    - Set up CI/CD workflows using Docker and GitHub Actions.

  ## 🛠️ Technical Stack & Skills
  - **Languages**: Python, C++, TypeScript, SQL.
  - **Frameworks & Tools**: FastAPI, React, Node.js, Docker, Git, Linux.

  ## 🌐 Languages
  - **Spanish**: Native.
  - **English**: Fluent / C1 (full professional proficiency).

  ## 🎯 Career Preferences
  - Target Roles: Backend Developer, Software Engineer Junior/Mid, Data Engineer.
  - Accepted Modalities: Remote or Hybrid.
  ```

### 5.2. Step 2: Ranking Rules & Policy (`ranking_policy.md`)
* **Path**: [`profile/ranking_policy.md`](profile/ranking_policy.md)
* **Format**: Markdown (`.md`)
* **Purpose**: Defines the scoring rules (0 to 100) followed by the ranker LLM.
* **Structure**:
  - **Level 1 (Technical Affinity)**: Points for stack alignment (+20 to +40).
  - **Level 2 (Seniority Match)**: Points for fitting candidate experience (+10 to +20).
  - **Level 3 (Work Mode & Location)**: Bonuses for preferred arrangements.
  - **Penalties**: Deductions for missing mandatory qualifications.

### 5.3. Step 3: Engine Pipeline Parameters (`pipeline_config.json`)
* **Path**: [`profile/pipeline_config.json`](profile/pipeline_config.json)
* **Format**: JSON
* **Complete Example**:
  ```json
  {
    "language": "en",
    "max_jobs_per_board": 5,
    "delay_between_batches_seconds": 3.0,
    "delay_between_boards_seconds": 10.0,
    "max_years_experience": 3,
    "auto_pipeline_execution": true
  }
  ```
* **Property Descriptions**:
  - `"language"`: Reporting and fit rationale language (`"es"`, `"en"`, or `null` to prompt).
  - `"max_jobs_per_board"`: Maximum new vacancies to rank per query (`null` for no cap).
  - `"delay_between_batches_seconds"`: Pause between ranking batches (prevents `429` quota errors).
  - `"delay_between_boards_seconds"`: Pause between boards in multi-board executions.
  - `"max_years_experience"`: Experience threshold (drops jobs requiring more years).
  - `"auto_pipeline_execution"`: `true` automatically runs the 6-stage pipeline without confirmation delays.

### 5.4. Step 4: Location & Work Mode Filters (`location_filters.json`)
* **Path**: [`profile/location_filters.json`](profile/location_filters.json)
* **Format**: JSON
* **Complete Example**:
  ```json
  {
    "work_modes": {
      "allow_remote": true,
      "allow_hybrid": true,
      "allow_onsite": false,
      "allow_unspecified": true
    },
    "location_preferences": {
      "allow_unspecified_location": true,
      "allowed_countries": [
        "Argentina"
      ],
      "allowed_cities": [
        "Buenos Aires",
        "CABA"
      ],
      "allowed_remote_regions": [
        "LATAM",
        "Americas",
        "Worldwide",
        "Anywhere"
      ],
      "blocked_countries": [
        "India",
        "China",
        "Philippines"
      ]
    }
  }
  ```

### 5.5. Step 5: Pre & Post-Parse Blacklists (`*.md`)
* **Paths**:
  - Pre-Parse (0 tokens): [`profile/title_blacklist.md`](profile/title_blacklist.md), [`profile/department_blacklist.md`](profile/department_blacklist.md)
  - Post-Parse (0 tokens): [`profile/blacklist_roles.md`](profile/blacklist_roles.md), [`profile/blacklist_seniority.md`](profile/blacklist_seniority.md)
* **Format**: Markdown bullet list (`- Term`). Matches whole words case-insensitively (`\bterm\b`).
* **Example (`profile/title_blacklist.md`)**:
  ```markdown
  # Title Blacklist
  - Sales
  - Marketing
  - Recruiter
  - Account Executive
  - Chief
  - Vice President
  - Director
  ```
* **Example (`profile/blacklist_seniority.md`)**:
  ```markdown
  # Seniority Blacklist
  - Senior
  - Lead
  - Staff
  - Principal
  - Director
  - Manager
  ```

### 5.6. Step 6: Board URL Registry (`board_urls.json`)
* **Path**: [`profile/board_urls.json`](profile/board_urls.json)
* **Format**: JSON (Manageable directly or via chat commands `add_board_url` and `delete_board_url`).
* **Example**:
  ```json
  [
    {
      "id": "board_exactasuba",
      "name": "Exactas UBA",
      "url": "https://exactas.uba.ar/ofertas-de-trabajo-profesional/ofertas-activas-estudiantes/",
      "source_type": "exactas",
      "last_analyzed": null,
      "created_at": "2026-08-18T00:00:00",
      "notes": "Official FCEyN UBA board"
    },
    {
      "id": "board_invgate",
      "name": "InvGate",
      "url": "https://boards-api.greenhouse.io/v1/boards/invgate/jobs?content=true",
      "source_type": "greenhouse",
      "last_analyzed": "2026-08-17T22:23:37",
      "created_at": "2026-08-06T04:01:51",
      "notes": ""
    }
  ]
  ```

---

## 🛠️ Modular Tool Suite (`HERRAMIENTAS_BASICAS`)

The master conversational orchestrator `jobbud_agent` operates exclusively through its **23 modular tools**:

| Domain | Tool Name | Description |
| :--- | :--- | :--- |
| **Queries** | `check_existing_job` | Checks deduplication by ID, title, or URL in `jobs.json`. |
| **Queries** | `get_job_raw_text` | Retrieves the complete unparsed raw text of a stored vacancy. |
| **Queries** | `get_job_details` | Returns structured vacancy record, fit rationale, and direct application URL. |
| **Queries** | `get_top_job_recommendations` | Lists Top N ranked opportunities ordered by fit score (excluding applied/disqualified). |
| **Queries** | `list_jobs_by_status` | Lists stored vacancies filtered by status (`ranked`, `applied`, `disqualified`). |
| **Queries** | `filter_jobs_by_blacklist` | Evaluates job postings against title and role blacklists. |
| **Queries** | `filter_job_by_location` | Checks country, city, and modality against `location_filters.json`. |
| **Management** | `mark_job_status` | Updates position lifecycle status (`applied`, `disqualified`, `ranked`). |
| **Management** | `delete_job_from_json` | Deletes a job position from `jobs.json`. |
| **Management** | `revert_last_job_action` | Reverts the last status change or deletion using automatic backups. |
| **Management** | `execute_job_pipeline_tool` | Runs the sequential batch ranking pipeline for a single board or selection. |
| **Management** | `execute_multi_board_pipeline_tool` | Runs the automated multi-board sequential pipeline with timers and Top 5 summary. |
| **Management** | `set_language_preference` | Configures and persists language preference (`es` / `en`) in `pipeline_config.json`. |
| **Management** | `get_language_preference` | Retrieves currently configured language from `pipeline_config.json`. |
| **Fetchers** | `fetch_greenhouse_job_content` | Queries Greenhouse REST API portals (0 LLM tokens). |
| **Fetchers** | `fetch_ashby_job_content` | Queries Ashby HQ Public API portals (0 LLM tokens). |
| **Fetchers** | `fetch_lever_job_content` | Queries Lever Public API portals (0 LLM tokens). |
| **Fetchers** | `fetch_exactas_job_board` | Scrapes and normalizes vacancies from Exactas UBA job board. |
| **Fetchers** | `fetch_linkedin_job_content` | Extracts content and normalizes public LinkedIn job postings. |
| **Boards** | `add_board_url` | Registers a new job board URL (`greenhouse`, `ashby`, `lever`, `exactas`). |
| **Boards** | `list_job_boards` | Lists all registered boards sorted from oldest/unanalyzed to newest. |
| **Boards** | `get_board_to_analyze` | Resolves and analyzes a board by number or name, updating `last_analyzed`. |
| **Boards** | `delete_board_url` | Removes a registered job board by number, ID, or name. |

---

## 🚀 Installation & Setup

### 7.1. Prerequisites & Installation

* **Python 3.10** or higher.
* Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/)).

```bash
git clone https://github.com/your-username/jobbud.git
cd jobbud

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 7.2. Environment Configuration (`.env`)

Create or edit the `.env` file in the project root:

```env
GOOGLE_API_KEY=your_google_gemini_api_key_here
DEFAULT_MODEL=gemini-3.1-flash-lite
ADK_DEFAULT_APP_NAME=src
```

### 7.3. Running JobBud (CLI vs Web ADK)

#### Option A: Command-Line Interface (CLI)
```bash
python main.py
```

#### Option B: ADK Web Interface (Google Agent Development Kit Web)
```bash
adk web src
```

---

## 💬 Example Conversational Commands

* **List and View Registered Boards**:
  > *"show my boards"* or *"list boards"*
* **Analyze a Specific Board**:
  > *"analyze board 1"* or *"analyze InvGate"*
* **Run Automated Multi-Board Search**:
  > *"analyze all my boards"* or *"analyze boards unanalyzed this month"*
* **View Full Vacancy Details & Application Instructions**:
  > *"give me details for greenhouse_invgate_4495272002"* or *"how do I apply to the Neix position?"*
* **View Top Accumulated Recommendations**:
  > *"show me the top 5 positions to apply"*
* **Manage Application Status**:
  > *"mark vacancy X as applied"* or *"disqualify vacancy Y"*
* **Undo Last Action**:
  > *"undo"* or *"revert"*
* **Register a New Job Board**:
  > *"add Ashby board for Linear: https://jobs.ashbyhq.com/linear"*

---

## 🛡️ Data Integrity & Persistence

1. **3-Level Automatic Deduplication**:
   - Before parsing or ranking, JobBud checks `jobs.json` by ID, URL, and title match to avoid redundant LLM evaluations and save 100% of tokens on existing jobs.
2. **Source Data Immutability**:
   - During ranking, all original posting metadata (`title`, `company`, `location`, `raw_text`, `source_url`) remains immutable, updating only evaluation fields (`score`, `justification`, `strengths`, `gaps`, `status`).
3. **Backup & Instant Reversibility (`revert_last_job_action`)**:
   - Any status update (`applied`, `disqualified`) or deletion automatically generates an action backup in `.last_job_action_backup.json`, enabling immediate undo functionality.
