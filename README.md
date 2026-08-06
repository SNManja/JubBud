# 💼 JobBud — Intelligent Job Search Assistant with Google ADK

[![English](https://img.shields.io/badge/Language-English-red.svg)](README.md) [![Spanish](https://img.shields.io/badge/Language-Español-blue.svg)](README.es.md)

**JobBud** is a conversational agent and master orchestrator designed to automate job searching, filtering, evaluation, and application lifecycle management for Computer Science students and Software Engineers.

The system ingests job postings from multiple sources (Greenhouse portal APIs, Exactas UBA web scraping, LinkedIn links, or raw text), applies a **two-stage deterministic Python filtering process (0 tokens)**, evaluates fit match (*score 0–100*) against a candidate profile (`profile/candidate_profile.md`) using batch LLM subagents, and manages the full application lifecycle in `jobs.json`.

---

## 🏛️ System Architecture (6 Master Stages)

```text
                     Job Posting / Link / Portal API Query
                                    │
                                    ▼
           [STAGE 1: DATA ACQUISITION (API / Web Scraping)]
           - Fetches API (e.g. Greenhouse) or receives raw text.
                                    │
                                    ▼
           [STAGE 2: PRE-PARSE HARD FILTER (Python / 0 Tokens)]
           - Filters by `title_blacklist.md`, `department_blacklist.md`, and `location_filters.json`.
           - Displays numbered list (1 to N) of candidate jobs in chat.
           - ⛔ MANDATORY PAUSE: Wait for explicit user selection in chat ("1, 3", "all").
                                    │
                                    ▼
           [STAGE 3: PARSING & IN-MEMORY STRUCTURING]
           - Structures selected jobs into memory dicts (via API or `job_parser_agent`).
                                    │
                                    ▼
           [STAGE 4: POST-PARSE DETERMINISTIC FILTER (Python / 0 Tokens)]
           - Filters by `blacklist_roles.md`, `blacklist_seniority.md`, and `location_filters.json`.
           - If role/seniority/country fails -> Immediate discard (0 writes, 0 ranking tokens).
                                    │
                                    ▼
           [STAGE 5: BATCH RANKING VIA LLM SUBAGENT (`job_ranker_agent`)]
           - Splits valid jobs into chunks of size k = min(5, ceil(R / 4)).
           - Each chunk is evaluated by `job_ranker_agent` in a single subagent turn.
                                    │
                                    ▼
           [STAGE 6: ATOMIC SAVE TO `jobs.json`]
           - Persists only successfully ranked positions in `jobs.json` (`status: "ranked"`).
```

---

## ✨ Key Features

1. **Extreme Token Efficiency (Dual Deterministic Filters)**:
   - **Pre-Parse**: Discards unapproved job titles, departments, or countries directly from API metadata without calling LLMs.
   - **Post-Parse**: Discards jobs with incompatible seniority (`Senior`, `Lead`) or non-technical roles (`Sales`, `Recruiter`) in Python before LLM ranking.

2. **In-Memory Caching & Quota Limit Prevention**:
   - `LAST_FETCHED_JOBS_CACHE` stores full job dictionaries in Python memory.
   - The agent transmits short selection strings (e.g. `job_items_or_selection="1, 3"`), preventing giant JSON payloads in prompts and eliminating `429 RESOURCE_EXHAUSTED` errors.

3. **Deterministic Job Board Registry (`profile/board_urls.json`)**:
   - Persistent registry of job board URLs sorted deterministically: **never analyzed first**, followed by least recently analyzed.
   - Formatted output with relative Spanish timestamps (*"Hoy (06/08/2026 a las 04:02 hs)"*, *"Nunca"*).

4. **Extensive Vacancy Inspection & Direct Application Links (`get_job_details`)**:
   - When inspecting any stored position, the agent retrieves all structured fields and explicitly provides the **direct application URL (`source_url`)** and **application instructions (`application_method`)**.

5. **Status & Application Lifecycle Management**:
   - Allows classifying jobs as descalificadas (`disqualified`) or aplicadas (`applied`), deleting positions, or reverting recent actions (`revert_last_job_action`).

6. ⛔ **Zero Mock Data Policy**:
   - Strict prohibition against creating or persisting mock or synthetic test jobs (`test_adk_rank_1`) in `jobs.json`.

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
│   ├── board_urls.json          # Persistent job board registry
│   ├── location_filters.json    # Allowed/blocked countries and remote rules
│   ├── title_blacklist.md       # Pre-Parse title blacklist
│   ├── department_blacklist.md  # Pre-Parse API department blacklist
│   ├── blacklist_roles.md       # Post-Parse role/area blacklist
│   └── blacklist_seniority.md   # Post-Parse seniority blacklist
└── src/
    ├── agent.py                 # Main `jobbud_agent` instance (Google ADK Agent)
    ├── config.py                # Environment variable loader (.env)
    ├── guidelines.md            # System prompt & conversational guidelines
    ├── subagents/
    │   ├── job_parser/          # Job parsing & structuring subagent
    │   ├── job_ranker/          # Fit match evaluation & scoring subagent
    │   └── job_pipeline/        # Deterministic sequential runner (`runner.py`)
    └── tools/                   # Modular collection of 18 tools
        ├── __init__.py          # Re-exports HERRAMIENTAS_BASICAS
        ├── fetchers.py          # API connectors & web scraping (Greenhouse, Exactas, LinkedIn)
        ├── queries.py           # Job querying, detailed inspection & filters
        ├── management.py        # Status edits, deletions, undo & pipeline tool
        └── boards.py            # Job board registry management & ordering
```

---

## ⚙️ Profile Configuration & Filters (`profile/`)

All candidate configuration and filtering rules are located in the [`profile/`](file:///home/santi/jobbud/profile/) directory:

| File | Role / Type | Pipeline Stage | Description & Filtering Rules |
| :--- | :--- | :--- | :--- |
| **[`profile/candidate_profile.md`](file:///home/santi/jobbud/profile/candidate_profile.md)** | Professional Profile | **Stage 5 (LLM Ranking)** | Defines academic background (CS Student UBA), tech stack (Python, C++, SQL), English level (C2), and preferences. Used by `job_ranker_agent` to compute fit match score (0-100). |
| **[`profile/board_urls.json`](file:///home/santi/jobbud/profile/board_urls.json)** | Job Board Registry | **Stage 1 (Data Acquisition)** | Persistent JSON store of registered job board URLs (Greenhouse, Ashby, etc.) and analysis timestamps. Managed deterministically by `src/tools/boards.py`. |
| **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)** | **Pre-Parse Hard Filter** | **Stage 2 (Python / 0 Tokens)** | Blacklist terms matched against the raw job title. Omits non-target jobs like *Sales, Recruiter, HR, Director, Chief, Manager* before parsing. |
| **[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)** | **Pre-Parse Hard Filter** | **Stage 2 (Python / 0 Tokens)** | Blacklist terms matched against API department metadata. Omits non-technical areas (e.g. *Customer Service, Marketing, Finance*). |
| **[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | **Location & Country Filter** | **Stages 2 & 4 (Python / 0 Tokens)** | Specifies allowed countries (`allowed_countries`: `["Argentina"]`), blocked countries (`blocked_countries`), remote regions, and `allow_unspecified_location` rule. |
| **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)** | **Post-Parse Filter** | **Stage 4 (Python / 0 Tokens)** | Blacklist terms matched against structured role/area fields (e.g. *Human Resources, Sales Representative, Commercial, UX/UI Design*). |
| **[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)** | **Post-Parse Filter** | **Stage 4 (Python / 0 Tokens)** | Blacklist terms matched against structured seniority levels. Discards jobs assigned to *Senior, Lead, Staff, Principal, Director, Manager*. |

---

## 🛠️ Core Tools (`HERRAMIENTAS_BASICAS`)

`jobbud_agent` is equipped with **18 modular tools**:

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
| `execute_job_pipeline_tool` | Management | Runs the deterministic sequential filtering and batch ranking runner. |
| `fetch_linkedin_job_content` | Fetchers | Extracts content from LinkedIn job posts. |
| `fetch_exactas_job_board` | Fetchers | Fetches job postings from Exactas UBA job board. |
| `fetch_greenhouse_job_content` | Fetchers | Fetches job listings via Greenhouse portal API. |
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
