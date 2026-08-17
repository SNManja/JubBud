# 💼 JobBud — Asistente Inteligente de Búsqueda Laboral con Google ADK

[![Spanish](https://img.shields.io/badge/Language-Español-blue.svg)](README.es.md) [![English](https://img.shields.io/badge/Language-English-red.svg)](README.md) [![Ejemplo de Salida Real](https://img.shields.io/badge/Ejemplo_Real-Ver_Reporte-green.svg)](EXAMPLE_OUTPUT.md)

> 📊 **[Hacé clic acá para ver un ejemplo de reporte real de procesamiento multitablero (29 tableros analizados)](EXAMPLE_OUTPUT.md)**

**JobBud** es un agente conversacional y orquestador maestro diseñado para automatizar la búsqueda, filtrado, evaluación y gestión de postulaciones laborales para estudiantes e ingenieros en Ciencias de la Computación.

El sistema procesa ofertas laborales desde múltiples fuentes (APIs de portales como Greenhouse, scraping de Exactas UBA, links de LinkedIn o texto crudo), aplica un **filtrado determinista de dos etapas en Python (0 tokens)**, evalúa el ajuste (*fit score 0–100*) de cada vacante contra el perfil del candidato (`profile/candidate_profile.md`) mediante subagentes LLM en lote, y gestiona el ciclo de vida completo de las postulaciones en `jobs.json`.

---

## 🏛️ Arquitectura del Sistema (6 Etapas Maestras)

```text
                     Aviso / Link / Consulta de Portal API
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 1. Capa de Ingesta Unificada (`src/fetchers/`)              │
       │ - greenhouse.py: API -> List[JobDict] (0 tokens LLM)        │
       │ - ashby.py: API -> List[JobDict] (0 tokens LLM)             │
       │ - exactas.py: Scrapes UBA -> llama a job_parser_agent       │
       │ - linkedin.py: Obtiene HTML -> llama a job_parser_agent     │
       │ - manual.py: Ingesta texto crudo -> llama a job_parser_agent│
       │ -> Contrato de Salida: List[JobDict] Estandarizado          │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 2. Pre-Filtro Duro Inicial (Pre-LLM Python / 0 Tokens)      │
       │ (title_blacklist, department_blacklist, location_filters)   │
       │ - Registra vacantes crudas (total_raw) y descartadas        │
       │ - Carga vacantes conservadas en Caché (`LAST_FETCHED_...`)  │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 3. Normalización Estructurada en Memoria                     │
       │ - Confirma JobDicts normalizados en memoria con IDs estables │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │ 4. Filtro Post-Parseo, Dedupe por Invariante & Board Cap    │
       │ (blacklist_roles, blacklist_seniority, location, max_years) │
       │ - Post-Parse: Descarta roles y seniorities prohibidos.      │
       │ - Filtro Semántico YOE: Descarta si YOE numérico > max_years│
       │ - Dedupe: Omite vacantes ya existentes en jobs.json (0 tok).│
       │ - Cap Opcional: max_jobs_per_board limita vacantes nuevas.  │
       └────────────────────────────┬────────────────────────────────┘
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
       [Falla Filtro / Ya en jobs.json / Capped]  [Vacante Nueva & Pasa Filtros]
                │                                       │
       Descartar / Omitir                       5. Rankeo en Lotes vía ADK `job_ranker_agent`
       (0 tokens de rankeo, 0 escrituras)          - Registra `set_ranking_batch_cache(chunk)`
                                                   - Tamaño de lote: k = min(5, ceil(R/4))
                                                   - Pausa entre lotes: delay_between_batches_seconds
                                                   - Limpia `clear_ranking_batch_cache()` en `finally`
                                                        │
                                                        ▼
                                                6. Merge Determinista & Persistencia en jobs.json
                                                   - `save_ranked_jobs_batch` une el JobDict de memoria
                                                     con la evaluación del ranker (score, justificación, etc.).
                                                   - Valida que el ID pertenezca al lote y sea nuevo.
                                                   - Persiste registro 100% completo en `jobs.json`.
                                                        │
                                                        ▼
                                                Entrega Reporte Markdown
```

---

## ✨ Características Principales

1. **Capa de Ingesta Unificada (`src/fetchers/`)**:
   - Encapsula la lógica de obtención por portal en módulos especializados (`greenhouse.py`, `ashby.py`, `exactas.py`, `linkedin.py`, `manual.py`).
   - Todos los fetchers cumplen un contrato estándar devolviendo `List[JobDict]`, garantizando que todas las etapas posteriores reciban datos homogéneos.
   - Los fetchers son los **únicos que invocan** a `job_parser_agent`.

2. **Filtros Deterministas Duales y Cero Desperdicio de Tokens**:
   - **Etapa 2 (Pre-Parseo)**: Descarta títulos, áreas o ubicaciones no deseadas directamente de los metadatos crudos con **0 tokens LLM**.
   - **Etapa 4 (Post-Parseo)**: Descarta seniorities incompatibles (`Senior`, `Lead`), roles no técnicos (`Sales`, `Recruiter`) y puestos que excedan `max_years_experience` en Python antes del rankeo.

3. **Extracción Semántica de Experiencia y Seniority (Sin Falsos Positivos por Regex)**:
   - Los años de experiencia requeridos (`years_of_experience`) y el nivel de seniority son extraídos semánticamente por `job_parser_agent` usando comprensión de lenguaje natural, eliminando expresiones regulares frágiles que confundían la historia de la empresa con los requisitos del puesto.
   - El filtro de la Etapa 4 solo descarta si un valor numérico explícito supera `max_years_experience`.

4. **Arquitectura Modular del Pipeline (`src/subagents/job_pipeline/`)**:
   - Desacoplado en submódulos de responsabilidad única: `single_pipeline.py`, `multi_pipeline.py`, `adk_clients.py`, `config.py`, `state.py`, `scope_parser.py` y `reporter.py`.
   - Propaga 8 métricas explícitas de telemetría: `total_raw`, `pre_discarded_count`, `post_discarded_count`, `deduped_count`, `capped_count`, `sent_to_ranker_count`, `successfully_ranked_count` y `ranking_errors_count`.

5. **Ejecución Automática y Control de Rate Limits**:
   - Ejecuta el pipeline completo de forma autónoma sin pausas de confirmación manuales innecesarias.
   - `max_jobs_per_board` en `profile/pipeline_config.json` limita el máximo de vacantes a evaluar por consulta.
   - `delay_between_batches_seconds` y `delay_between_boards_seconds` aplican pausas configurables para prevenir bloqueos de cuota (`429`).

6. **IDs Canónicas y Deduplicación por Invariante**:
   - **Esquema de IDs**: IDs estables (`greenhouse_{board}_{id}`, `ashby_{company}_{id}`, `exactas_{num}`, `linkedin_{id}` y hashes MD5 `manual_{md5(empresa:titulo)[:8]}`).
   - **Deduplicación por Invariante**: Vacantes ya guardadas en `jobs.json` son omitidas automáticamente antes de consumir slots de rankeo.

7. **Inspección Exhaustiva y Métodos de Postulación (`get_job_details`)**:
   - Recupera el detalle completo, justificación de fit, fortalezas, vacíos y el **link directo (`source_url`) junto con las instrucciones de postulación (`application_method`)** con fallback en 4 niveles.

8. **Soporte Multi-Idioma e Internacionalización Dinámica**:
   - Configurable en `profile/pipeline_config.json` (`"language": "es" | "en" | null`).
   - Si el idioma no está configurado o es inválido, `jobbud_agent` le pregunta al usuario y persiste su elección usando `set_language_preference`.
   - Genera reportes de telemetría en el idioma configurado vía `src/subagents/job_pipeline/reporter.py`.
   - Invariante: `job_parser_agent` se mantiene agnóstico al usuario y centrado en la publicación, mientras que `job_ranker_agent` evalúa y redacta sus justificaciones en el idioma elegido por el usuario.

9. **Contrato Estricto de Esquema JSON para `strengths` y `gaps`**:
   - `strengths` y `gaps` están garantizados como listas planas `List[str]` (`["texto 1", "texto 2"]`).
   - Normalización determinista en Python (`_normalize_string_list`) asegura que nunca se guarden objetos anidados en `jobs.json`.

10. ⛔ **Política Cero Mock Data**:
    - Prohibición estricta de generar o persistir datos ficticios (`test_adk_rank_1`) en `jobs.json`.

---

## 📂 Estructura del Proyecto

```text
jobbud/
├── main.py                      # Ejecutor CLI principal interactivo (InMemoryRunner)
├── jobs.json                    # Base de datos central en formato JSON unificado
├── README.md                    # Documentación del proyecto (Inglés)
├── README.es.md                 # Documentación del proyecto (Español)
├── GEMINI.md                    # Especificación de arquitectura y reglas del agente
├── profile/                     # Perfil del candidato y reglas de filtrado
│   ├── candidate_profile.md     # Perfil profesional y preferencias del usuario
│   ├── ranking_policy.md        # Jerarquía de reglas, scoring y política del usuario
│   ├── pipeline_config.json     # Límites del pipeline (idioma, cap por board, timer de lote, exp máx, auto flag)
│   ├── board_urls.json          # Registro persistente de tableros de empleo
│   ├── location_filters.json    # Países permitidos, ciudades/barrios y reglas remotas
│   ├── title_blacklist.md       # Términos excluidos en títulos (Pre-Parseo)
│   ├── department_blacklist.md  # Áreas excluidas en metadatos (Pre-Parseo)
│   ├── blacklist_roles.md       # Roles/áreas excluidas (Post-Parseo)
│   └── blacklist_seniority.md   # Seniorities excluidos (Post-Parseo)
└── src/
    ├── agent.py                 # Instancia principal de `jobbud_agent` (Google ADK Agent con 22 tools, 0 subagents)
    ├── config.py                # Carga centralizada de variables de entorno (.env)
    ├── guidelines.md            # Instrucciones del sistema y directivas conversacionales
    ├── fetchers/                # Capa de Ingesta Unificada que retorna List[JobDict]
    │   ├── __init__.py          # Exporta funciones de fetcher y herramientas del agente
    │   ├── base.py              # Compresión de texto y extractor de tecnologías
    │   ├── greenhouse.py        # Conector API REST de Greenhouse (0 tokens LLM)
    │   ├── ashby.py             # Conector API REST de Ashby HQ (0 tokens LLM)
    │   ├── exactas.py           # Scraper FCEyN UBA + integración con parser
    │   ├── linkedin.py          # Extractor de avisos de LinkedIn + integración con parser
    │   └── manual.py            # Normalizador de texto crudo + integración con parser
    ├── subagents/
    │   ├── job_parser/          # Subagente extractor y estructurador (worker programático)
    │   │   ├── job_parser.py    # Definición de Agente ADK
    │   │   ├── guidelines.md    # Esquema de extracción (incluye commitment y YOE)
    │   │   └── tools.py         # Generador de IDs, métodos de postulación y constructor de JobDict
    │   ├── job_ranker/          # Subagente evaluador de compatibilidad (worker en lotes)
    │   │   ├── job_ranker.py    # Definición de Agente ADK
    │   │   ├── guidelines.md    # Criterios y directivas de rankeo
    │   │   └── tools.py         # Lectores de perfil/política y persistencia en lote
    │   └── job_pipeline/        # Pipeline secuencial determinista modular
    │       ├── __init__.py      # Re-exporta puntos de entrada del pipeline
    │       ├── runner.py        # Fachada para compatibilidad regresiva
    │       ├── single_pipeline.py # Runner secuencial de 6 etapas para un tablero o selección
    │       ├── multi_pipeline.py  # Orquestador multi-tablero y timers de espera
    │       ├── adk_clients.py   # Puente con ADK InMemoryRunner y backoff para cuota 429
    │       ├── config.py        # Lector de configuración del pipeline
    │       ├── state.py         # Manejo de caché y selector de índices
    │       ├── scope_parser.py  # Parser de scopes, fechas relativas e índices
    │       └── reporter.py      # Formateador de telemetría y reportes Markdown (i18n)
    └── tools/                   # Colección modular de 22 herramientas
        ├── __init__.py          # Exporta HERRAMIENTAS_BASICAS (las 22 herramientas)
        ├── queries.py           # Consultas, inspecciones detalladas y filtros deterministas
        ├── management.py        # Edición de estados, borrado, idioma, undo y herramientas de pipeline
        └── boards.py            # Registro y ordenamiento determinista de tableros
```

---

## 👤 Cómo Adaptar JobBud a Tu Perfil (`profile/`)

> **La arquitectura de JobBud es 100% genérica.** **NUNCA** tenés que modificar código fuente en Python (`src/`), ni las instrucciones de los agentes (`guidelines.md`), ni la lógica del pipeline para adaptar el sistema a un nuevo candidato.
> 
> **Para adaptar JobBud a tu propio perfil profesional, únicamente tenés que modificar los archivos dentro de la carpeta [`profile/`](file:///home/santi/jobbud/profile/).**

El siguiente esquema ilustra cómo cada archivo de `profile/` altera el proceso en cada una de las 6 etapas del pipeline:

```text
Portales de empleo (profile/board_urls.json)
        │
        ▼  [Etapa 1: Obtención de Datos (Data Acquisition)]
Listas negras de títulos, departamentos y ubicación (title_blacklist.md, department_blacklist.md, location_filters.json)
        │
        ▼  [Etapa 2: Filtrado Duro Pre-Parseo (0 Tokens LLM)]
Subagente Job Parser
        │
        ▼  [Etapa 3: Parseo y Estructuración LLM]
Límites por rol, seniority y años de experiencia (blacklist_roles.md, blacklist_seniority.md, pipeline_config.json)
        │
        ▼  [Etapa 4: Filtrado Duro Post-Parseo (0 Tokens LLM)]
Perfil del Candidato y Política de Rankeo (candidate_profile.md, ranking_policy.md)
        │
        ▼  [Etapa 5: Evaluación y Rankeo LLM (Score 0-100)]
Vacantes evaluadas guardadas en jobs.json
```

### Desglose por Etapa del Pipeline:

| Etapa del Pipeline | Archivo(s) de `profile/` | Cómo altera el proceso |
| :--- | :--- | :--- |
| **Etapa 1 (Obtención de Datos)** | **[`profile/board_urls.json`](file:///home/santi/jobbud/profile/board_urls.json)** | Registra los portales de empleo guardados (Greenhouse, Ashby, LinkedIn, etc.) de donde el sistema descarga las vacantes. |
| **Etapa 2 (Filtro Pre-Parseo)** | **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)**<br>**[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)**<br>**[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | Filtro Python determinista contra títulos crudos, departamentos de API y reglas de ubicación. Descarta vacantes fuera de foco con **0 costo de tokens LLM**. |
| **Etapa 4 (Filtro Post-Parseo)** | **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)**<br>**[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)**<br>**[`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json)** | Filtro Python determinista contra campos parseados. Descarta roles no deseados, seniorities incompatibles o empleos que superan `max_years_experience`. |
| **Etapa 5 (Rankeo LLM)** | **[`profile/candidate_profile.md`](file:///home/santi/jobbud/profile/candidate_profile.md)**<br>**[`profile/ranking_policy.md`](file:///home/santi/jobbud/profile/ranking_policy.md)** | El subagente `job_ranker_agent` lee dinámicamente el **perfil del candidato** y las **directivas de puntuación** para calcular el fit score exacto (0-100), justificación, fortalezas y vacíos. |

---

## ⚙️ Configuración del Perfil y Filtros (`profile/`)

Todos los archivos de configuración y filtrado residen en la carpeta [`profile/`](file:///home/santi/jobbud/profile/):

| Archivo | Tipo / Rol | Etapa de Aplicación | Descripción y Reglas de Filtrado |
| :--- | :--- | :--- | :--- |
| **[`profile/candidate_profile.md`](file:///home/santi/jobbud/profile/candidate_profile.md)** | Perfil Profesional | **Etapa 5 (Rankeo LLM)** | Define la formación académica (Computación UBA), experiencia laboral, stack técnico principal, nivel de inglés (C2) y expectativas. Utilizado por `job_ranker_agent` para calcular el fit score (0-100). |
| **[`profile/ranking_policy.md`](file:///home/santi/jobbud/profile/ranking_policy.md)** | Política de Rankeo | **Etapa 5 (Rankeo LLM)** | Define la jerarquía de reglas elegidas por el usuario (Niveles 1-8), políticas de separación entre scoring y recall, y reglas de formato para fortalezas y vacíos. |
| **[`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json)** | Configuración del Pipeline | **Etapas 4 y 5 (Reglas del Pipeline)** | Configura `max_jobs_per_board` (máximo de empleos a rankear por consulta), `delay_between_batches_seconds` (timer entre lotes), `delay_between_boards_seconds` (timer entre tableros), `max_years_experience` (máximo de años de experiencia permitidos, ej: 3) y `auto_pipeline_execution`. |
| **[`profile/board_urls.json`](file:///home/santi/jobbud/profile/board_urls.json)** | Registro de Tableros | **Etapa 1 (Obtención de Datos)** | Registro JSON persistente de las URLs de portales de empleo guardados (Greenhouse, Ashby, etc.) con sus fechas de análisis. Administrado determinísticamente por `src/tools/boards.py`. |
| **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)** | **Filtro Duro Pre-Parseo** | **Etapa 2 (Python / 0 Tokens)** | Lista negra de términos en el título original del puesto. Omite directamente vacantes como *Sales, Recruiter, HR, Director, Chief, Manager* antes de parsear. |
| **[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)** | **Filtro Duro Pre-Parseo** | **Etapa 2 (Python / 0 Tokens)** | Lista negra de departamentos/áreas presentes en los metadatos de la API del portal. Omite vacantes no técnicas (ej. *Customer Service, Marketing, Finance*). |
| **[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | **Filtro de Ubicación/País** | **Etapas 2 y 4 (Python / 0 Tokens)** | Define países permitidos (`allowed_countries`: `["Argentina"]`), ciudades/barrios permitidos para presencial/híbrido (`allowed_cities`), países bloqueados (`blocked_countries`), regiones remotas (`allowed_remote_regions`) y la regla para ubicaciones no especificadas (`allow_unspecified_location`). |
| **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)** | **Filtro Post-Parseo** | **Etapa 4 (Python / 0 Tokens)** | Lista negra por área o rol parseado estructurado (ej. *Human Resources, Sales Representative, Commercial, UX/UI Design*). |
| **[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)** | **Filtro Post-Parseo** | **Etapa 4 (Python / 0 Tokens)** | Lista negra por nivel de seniority parseado o por límite de experiencia (`years_of_experience > max_years_experience`). Descarta automáticamente vacantes asignadas a niveles *Senior, Lead, Staff, Principal, Director, Manager*. |

---

## 🛠️ Herramientas Registradas (`HERRAMIENTAS_BASICAS`)

El agente `jobbud_agent` dispone de **20 herramientas modulares**:

| Herramienta | Dominio | Propósito |
| :--- | :--- | :--- |
| `check_existing_job` | Queries | Verifica deduplicación por ID o URL en `jobs.json`. |
| `get_job_raw_text` | Queries | Recupera el texto crudo completo de la postulación. |
| `get_job_details` | Queries | Devuelve la ficha completa y el link directo de postulación. |
| `get_top_job_recommendations` | Queries | Lista el Top N mejores ofertas según puntaje de fit. |
| `list_jobs_by_status` | Queries | Lista empleos filtrados por estado (`ranked`, `applied`, `disqualified`). |
| `filter_jobs_by_blacklist` | Queries | Evalúa coincidencia contra listas negras. |
| `filter_job_by_location` | Queries | Filtra por país y modalidad. |
| `mark_job_status` | Management | Cambia el estado de una posición en `jobs.json`. |
| `delete_job_from_json` | Management | Elimina un puesto de `jobs.json`. |
| `revert_last_job_action` | Management | Deshace el último cambio de estado o eliminación. |
| `execute_job_pipeline_tool` | Management | Ejecuta el runner secuencial de filtrado y rankeo en lote. |
| `execute_multi_board_pipeline_tool` | Management | Ejecuta la pipeline secuencial multitablero automática con timers inter-board y reporte Top 5. |
| `fetch_linkedin_job_content` | Fetchers | Extrae contenido de publicaciones de LinkedIn. |
| `fetch_exactas_job_board` | Fetchers | Extrae vacantes del portal de empleos de Exactas UBA. |
| `fetch_greenhouse_job_content` | Fetchers | Consulta la API de portales Greenhouse. |
| `fetch_ashby_job_content` | Fetchers | Obtiene vacantes vía API pública de Ashby HQ. |
| `add_board_url` | Boards | Registra una nueva URL de tablero de empleo. |
| `list_job_boards` | Boards | Lista tableros ordenados de más antiguo a más reciente. |
| `get_board_to_analyze` | Boards | Resuelve y analiza un tablero por su número o nombre. |
| `delete_board_url` | Boards | Elimina un tablero del registro. |

---

## 🚀 Instalación y Uso

### 1. Requisitos Previos e Instalación

```bash
git clone https://github.com/usuario/jobbud.git
cd jobbud

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar Variables de Entorno

Crea o edita el archivo `.env` en la raíz del proyecto:

```env
GOOGLE_API_KEY=tu_api_key_de_google_gemini
DEFAULT_MODEL=gemini-3.1-flash-lite
ADK_DEFAULT_APP_NAME=src
```

### 3. Ejecución

#### Opción A: Interfaz de Línea de Comandos (CLI)

```bash
python main.py
```

#### Opción B: Interfaz Web ADK (Google Agent Development Kit Web)

```bash
adk web src
```

---

## 💬 Comandos Conversacionales de Ejemplo

- **Consultar Tableros Registrados**:
  > *"mis boards"* o *"listar tableros"*
- **Analizar un Tablero de Empleo**:
  > *"analizá el board 1"* o *"analizar board InvGate"*
- **Confirmar Selección de Vacantes**:
  > *"evaluá la 1 y la 3"* o *"todas"*
- **Ver Detalles y Método de Postulación de una Vacante**:
  > *"dame información sobre la vacante greenhouse_invgate_4495272002"*
- **Ver Mejores Recomendaciones**:
  > *"mostrame el top 5 para postularme"*
- **Marcar Empleo como Aplicado / Descalificado**:
  > *"marcar la vacante X como aplicada"*
- **Revertir Acción**:
  > *"deshacer"*
