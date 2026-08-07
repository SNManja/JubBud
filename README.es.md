# 💼 JobBud — Asistente Inteligente de Búsqueda Laboral con Google ADK

[![Spanish](https://img.shields.io/badge/Language-Español-blue.svg)](README.es.md) [![English](https://img.shields.io/badge/Language-English-red.svg)](README.md)

**JobBud** es un agente conversacional y orquestador maestro diseñado para automatizar la búsqueda, filtrado, evaluación y gestión de postulaciones laborales para estudiantes e ingenieros en Ciencias de la Computación.

El sistema procesa ofertas laborales desde múltiples fuentes (APIs de portales como Greenhouse, scraping de Exactas UBA, links de LinkedIn o texto crudo), aplica un **filtrado determinista de dos etapas en Python (0 tokens)**, evalúa el ajuste (*fit score 0–100*) de cada vacante contra el perfil del candidato (`profile/candidate_profile.md`) mediante subagentes LLM en lote, y gestiona el ciclo de vida completo de las postulaciones en `jobs.json`.

---

## 🏛️ Arquitectura del Sistema (6 Etapas Maestras)

```text
                     Aviso / Link / Consulta de Portal API
                                    │
                                    ▼
           [ETAPA 1: OBTENCIÓN DE DATOS (API / Web Scraping)]
           - Consulta API (ej. Greenhouse) o recibe texto crudo.
                                    │
                                    ▼
           [ETAPA 2: FILTRADO DURO PRE-PARSEO (Python / 0 Tokens)]
           - Filtra por `title_blacklist.md`, `department_blacklist.md` y `location_filters.json`.
                                    │
                  [ETAPA 3: PARSEO HÍBRIDO & ESTRUCTURACIÓN EN MEMORIA]
            - Vacantes de Job Boards (API): Pre-estructuradas en memoria Python (0 tokens LLM).
            - Texto crudo / Links: Parseados dinámicamente mediante `job_parser_agent` (LLM).
                                     │
                                     ▼
            [ETAPA 4: FILTRADO DETERMINISTA POST-PARSEO Y CAP POR BOARD (Python / 0 Tokens)]
            - Filtra por `blacklist_roles.md`, `blacklist_seniority.md` y `location_filters.json`.
            - Aplica el límite máximo `max_jobs_per_board` de `profile/pipeline_config.json`.
            - Si falla por rol, seniority o país -> Descarte inmediato (0 escrituras, 0 tokens de rankeo).
                                     │
                                     ▼
            [ETAPA 5: RANKEADO EN LOTES Y TIMER VÍA SUBAGENTE LLM (`job_ranker_agent`)]
            - Divide las vacantes retenidas en lotes de tamaño k = min(5, ceil(R / 4)).
            - Realiza una pausa de `delay_between_batches_seconds` entre llamadas de lote.
            - Cada lote es evaluado por `job_ranker_agent` en una sola llamada de subagente.
                                     │
                                     ▼
            [ETAPA 6: GUARDADO ATÓMICO EN `jobs.json`]
            - Persiste en `jobs.json` únicamente las vacantes rankeadas exitosamente (`status: "ranked"`).
```

---

## ✨ Características Principales

1. **Ahorro Extremo de Tokens (Filtros Duales y Parseo Híbrido)**:
   - **Pre-Parseo**: Descarta títulos, áreas o países no permitidos directamente en los metadatos de la API sin llamar al LLM.
   - **Parseo Híbrido en Etapa 3**: Reutiliza diccionarios pre-estructurados de las APIs a 0 tokens, y procesa de forma transparente vacantes en texto crudo mediante `job_parser_agent` para extraer campos clave (`title`, `company`, `seniority`, `key_technologies`) con LLM antes de filtrar.
   - **Post-Parseo**: Descarta puestos con seniority incompatible (`Senior`, `Lead`) o roles excluidos (`Sales`, `Recruiter`) en Python antes del rankeo.

2. **Ejecución Automática del Pipeline y Límite por Board**:
   - Ejecuta el filtrado y el rankeo en lotes automáticamente sin requerir pausas de confirmación en el chat.
   - `max_jobs_per_board` en `profile/pipeline_config.json` limita la cantidad máxima de empleos a evaluar por consulta evitando picos de consumo.
   - `delay_between_batches_seconds` añade una pausa configurable entre llamadas de lote al LLM para prevenir rate limits (`429`).

3. **IDs Estandarizadas por Plataforma y Arquitectura de Deduplicación en 3 Niveles**:
   - **Formato Canónico de IDs**: Generación determinista de IDs por plataforma (`greenhouse_{board}_{id}`, `exactas_{num}`, `linkedin_{id}`, y hashes MD5 para entradas manuales `manual_{md5(empresa:titulo)[:8]}`).
   - **Deduplicación en 3 Niveles**: Nivel 1 pre-verifica empleos existentes (`check_existing_job`), Nivel 2 omite inserciones duplicadas (`save_multiple_jobs_json`), y Nivel 3 realiza actualizaciones in-place (`upsert`) al guardar puntajes de rankeo (`save_ranked_jobs_batch`).

4. **Caché de Memoria y Prevención de Quota Limits**:
   - `LAST_FETCHED_JOBS_CACHE` almacena en memoria Python los diccionarios completos de los portales de empleo.
   - El agente transmite únicamente cadenas cortas de selección (ej: `job_items_or_selection="todas"`), impidiendo la generación de JSONs gigantes en los prompts.

4. **Gestión Determinista de Tableros (`profile/board_urls.json`)**:
   - Registro persistente de portales de empleo ordenados determinísticamente: **nunca analizados primero**, seguidos de los analizados hace más tiempo.
   - Salida formateada con fechas relativas en español (*"Hoy (06/08/2026 a las 04:02 hs)"*, *"Nunca"*).

5. **Inspección Extensa y Enlaces de Postulación Directos (`get_job_details`)**:
   - Al consultar cualquier vacante almacenada, el agente recupera todos los campos estructurados e incluye obligatoriamente el **link directo a la oferta (`source_url`)** y el **método explícito de postulación (`application_method`)**.

6. **Gestión de Estados y Deshacer (Undo)**:
   - Permite clasificar empleos como descalificados (`disqualified`) o aplicados (`applied`), eliminar registros o revertir la última acción (`revert_last_job_action`).

7. ⛔ **Política Cero Mock Data**:
   - Prohibición estricta de generar o persistir datos ficticios o de prueba (`test_adk_rank_1`) en `jobs.json`.

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
│   ├── pipeline_config.json     # Límites del pipeline (cap por board, timer de lote, auto flag)
│   ├── board_urls.json          # Registro persistente de tableros de empleo
│   ├── location_filters.json    # Países permitidos, bloqueados y reglas remotas
│   ├── title_blacklist.md       # Términos excluidos en títulos (Pre-Parseo)
│   ├── department_blacklist.md  # Áreas excluidas en metadatos (Pre-Parseo)
│   ├── blacklist_roles.md       # Roles/áreas excluidas (Post-Parseo)
│   └── blacklist_seniority.md   # Seniorities excluidos (Post-Parseo)
└── src/
    ├── agent.py                 # Instancia principal de `jobbud_agent` (Google ADK Agent)
    ├── config.py                # Carga centralizada de variables de entorno (.env)
    ├── guidelines.md            # Instrucciones del sistema y directivas conversacionales
    ├── subagents/
    │   ├── job_parser/          # Subagente extractor y estructurador de avisos
    │   ├── job_ranker/          # Subagente evaluador de compatibilidad (fit score)
    │   └── job_pipeline/        # Runner secuencial determinista (`runner.py`)
    └── tools/                   # Colección modular de 18 herramientas
        ├── __init__.py          # Exporta HERRAMIENTAS_BASICAS
        ├── fetchers.py          # Scraping y conectores API (Greenhouse, Exactas, LinkedIn)
        ├── queries.py           # Consultas, inspecciones detalladas y filtros
        ├── management.py        # Edición de estados, borrado, undo y runner tool
        └── boards.py            # Registro y ordenamiento determinista de tableros
```

---

## ⚙️ Configuración del Perfil y Filtros (`profile/`)

Todos los archivos de configuración y filtrado residen en la carpeta [`profile/`](file:///home/santi/jobbud/profile/):

| Archivo | Tipo / Rol | Etapa de Aplicación | Descripción y Reglas de Filtrado |
| :--- | :--- | :--- | :--- |
| **[`profile/candidate_profile.md`](file:///home/santi/jobbud/profile/candidate_profile.md)** | Perfil Profesional | **Etapa 5 (Rankeo LLM)** | Define la formación académica (Computación UBA), experiencia laboral, stack técnico principal, nivel de inglés (C2) y expectativas. Utilizado por `job_ranker_agent` para calcular el fit score (0-100). |
| **[`profile/pipeline_config.json`](file:///home/santi/jobbud/profile/pipeline_config.json)** | Configuración del Pipeline | **Etapas 4 y 5 (Reglas del Pipeline)** | Configura `max_jobs_per_board` (máximo de empleos a rankear por consulta), `delay_between_batches_seconds` (timer entre lotes), `delay_between_boards_seconds` (timer entre tableros), `max_years_experience` (máximo de años de experiencia permitidos, ej: 3) y `auto_pipeline_execution`. |
| **[`profile/board_urls.json`](file:///home/santi/jobbud/profile/board_urls.json)** | Registro de Tableros | **Etapa 1 (Obtención de Datos)** | Registro JSON persistente de las URLs de portales de empleo guardados (Greenhouse, Ashby, etc.) con sus fechas de análisis. Administrado determinísticamente por `src/tools/boards.py`. |
| **[`profile/title_blacklist.md`](file:///home/santi/jobbud/profile/title_blacklist.md)** | **Filtro Duro Pre-Parseo** | **Etapa 2 (Python / 0 Tokens)** | Lista negra de términos en el título original del puesto. Omite directamente vacantes como *Sales, Recruiter, HR, Director, Chief, Manager* antes de parsear. |
| **[`profile/department_blacklist.md`](file:///home/santi/jobbud/profile/department_blacklist.md)** | **Filtro Duro Pre-Parseo** | **Etapa 2 (Python / 0 Tokens)** | Lista negra de departamentos/áreas presentes en los metadatos de la API del portal. Omite vacantes no técnicas (ej. *Customer Service, Marketing, Finance*). |
| **[`profile/location_filters.json`](file:///home/santi/jobbud/profile/location_filters.json)** | **Filtro de Ubicación/País** | **Etapas 2 y 4 (Python / 0 Tokens)** | Define países permitidos (`allowed_countries`: `["Argentina"]`), ciudades/barrios permitidos para presencial/híbrido (`allowed_cities`), países bloqueados (`blocked_countries`), regiones remotas (`allowed_remote_regions`) y la regla para ubicaciones no especificadas (`allow_unspecified_location`). |
| **[`profile/blacklist_roles.md`](file:///home/santi/jobbud/profile/blacklist_roles.md)** | **Filtro Post-Parseo** | **Etapa 4 (Python / 0 Tokens)** | Lista negra por área o rol parseado estructurado (ej. *Human Resources, Sales Representative, Commercial, UX/UI Design*). |
| **[`profile/blacklist_seniority.md`](file:///home/santi/jobbud/profile/blacklist_seniority.md)** | **Filtro Post-Parseo** | **Etapa 4 (Python / 0 Tokens)** | Lista negra por nivel de seniority parseado o por límite de experiencia (`years_of_experience > max_years_experience`). Descarta automáticamente vacantes asignadas a niveles *Senior, Lead, Staff, Principal, Director, Manager*. |

---

## 🛠️ Herramientas Registradas (`HERRAMIENTAS_BASICAS`)

El agente `jobbud_agent` dispone de **19 herramientas modulares**:

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
