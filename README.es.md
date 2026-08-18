# 💼 JobBud — Asistente Inteligente de Búsqueda Laboral con Google ADK

[![Spanish](https://img.shields.io/badge/Language-Español-blue.svg)](README.es.md) [![English](https://img.shields.io/badge/Language-English-red.svg)](README.md) [![Ejemplo de Salida Real](https://img.shields.io/badge/Ejemplo_Real-Ver_Reporte-green.svg)](EXAMPLE_OUTPUT.md) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

> 📊 **[Hacé clic acá para ver un ejemplo de reporte real de procesamiento multitablero (29 tableros analizados)](EXAMPLE_OUTPUT.md)**

**JobBud** es un agente conversacional y orquestador maestro diseñado para automatizar la búsqueda, filtrado, evaluación y gestión de postulaciones laborales para profesionales y estudiantes técnicos.

El sistema procesa ofertas laborales desde múltiples fuentes (APIs de portales como Greenhouse, Ashby, Lever, scraping de Exactas UBA, links de LinkedIn o texto crudo), aplica un **filtrado determinista de dos etapas en Python (0 tokens)**, evalúa el ajuste (*fit score 0–100*) de cada vacante contra el perfil del candidato (`profile/candidate_profile.md`) mediante subagentes LLM en lote, y gestiona el ciclo de vida completo de las postulaciones en `jobs.json`.

---

## 📑 Índice de Contenidos

1. [🏛️ Arquitectura del Sistema (6 Etapas Maestras)](#️-arquitectura-del-sistema-6-etapas-maestras)
2. [✨ Características Principales](#-características-principales)
3. [📂 Estructura del Proyecto](#-estructura-del-proyecto)
4. [📐 Esquema y Contrato de Datos (`JobDict`)](#-esquema-y-contrato-de-datos-jobdict)
   - 4.1. [Especificación de Campos y Tipos](#41-especificación-de-campos-y-tipos)
   - 4.2. [Contrato de Fortalezas, Vacíos y Estados](#42-contrato-de-fortalezas-vacíos-y-estados)
   - 4.3. [Esquema de IDs Estables por Plataforma](#43-esquema-de-ids-estables-por-plataforma)
5. [👤 Guía de Configuración Paso a Paso (`profile/`)](#-guía-de-configuración-paso-a-paso-profile)
   - 5.1. [Paso 1: Tu Perfil Profesional (`candidate_profile.md`)](#51-paso-1-tu-perfil-profesional-candidate_profilemd)
   - 5.2. [Paso 2: Reglas y Política de Rankeo (`ranking_policy.md`)](#52-paso-2-reglas-y-política-de-rankeo-ranking_policymd)
   - 5.3. [Paso 3: Parámetros del Motor (`pipeline_config.json`)](#53-paso-3-parámetros-del-motor-pipeline_configjson)
   - 5.4. [Paso 4: Filtros de Ubicación y Modalidad (`location_filters.json`)](#54-paso-4-filtros-de-ubicación-y-modalidad-location_filtersjson)
   - 5.5. [Paso 5: Listas Negras Pre y Post-Parseo (`*.md`)](#55-paso-5-listas-negras-pre-y-post-parseo-md)
   - 5.6. [Paso 6: Registro de Tableros (`board_urls.json`)](#56-paso-6-registro-de-tableros-board_urlsjson)
6. [🛠️ Suite de Herramientas (`HERRAMIENTAS_BASICAS`)](#️-suite-de-herramientas-herramientas_basicas)
7. [🚀 Instalación y Puesta en Marcha](#-instalación-y-puesta-en-marcha)
   - 7.1. [Requisitos Previos e Instalación](#71-requisitos-previos-e-instalación)
   - 7.2. [Configurar Variables de Entorno (`.env`)](#72-configurar-variables-de-entorno-env)
   - 7.3. [Modos de Ejecución (CLI vs Web ADK)](#73-modos-de-ejecución-cli-vs-web-adk)
8. [💬 Comandos Conversacionales de Ejemplo](#-comandos-conversacionales-de-ejemplo)
9. [🛡️ Integridad de Datos y Persistencia](#️-integridad-de-datos-y-persistencia)

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
       │ - lever.py: API -> List[JobDict] (0 tokens LLM)             │
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
   - Encapsula la lógica de obtención por portal en módulos especializados (`greenhouse.py`, `ashby.py`, `lever.py`, `exactas.py`, `linkedin.py`, `manual.py`).
   - Todos los fetchers cumplen un contrato estándar devolviendo `List[JobDict]`, garantizando que todas las etapas posteriores reciban datos homogéneos.
   - Los fetchers de APIs (Greenhouse, Ashby, Lever) no consumen tokens LLM al estructurar vacantes; los de texto no estructurado (Exactas, LinkedIn, Manual) son los **únicos que invocan** a `job_parser_agent`.

2. **Filtros Deterministas Duales y Cero Desperdicio de Tokens**:
   - **Etapa 2 (Pre-Parseo)**: Descarta títulos, áreas o ubicaciones no deseadas directamente de los metadatos crudos con **0 tokens LLM**.
   - **Etapa 4 (Post-Parseo)**: Descarta seniorities incompatibles (`Senior`, `Lead`), roles no deseados (`Sales`, `Recruiter`) y puestos que excedan `max_years_experience` en Python antes del rankeo.

3. **Extracción Semántica de Experiencia y Seniority (Sin Regex Frágiles)**:
   - Los años de experiencia requeridos (`years_of_experience`) y el nivel de seniority son extraídos semánticamente por `job_parser_agent` usando comprensión de lenguaje natural, eliminando expresiones regulares que confunden la historia de la empresa con los requisitos del puesto.
   - El filtro de la Etapa 4 solo descarta si un valor numérico explícito supera `max_years_experience`.

4. **Arquitectura Modular del Pipeline (`src/subagents/job_pipeline/`)**:
   - Desacoplado en submódulos de responsabilidad única: `single_pipeline.py`, `multi_pipeline.py`, `adk_clients.py`, `config.py`, `state.py`, `scope_parser.py` y `reporter.py`.
   - Telemetría en tiempo real: reporta transparentemente vacantes crudas, descartadas en pre-filtro, conservadas, descartadas en post-filtro, deduplicadas, omitidas por tope y rankeadas con éxito.

5. **Ejecución Automática y Control de Rate Limits**:
   - Ejecuta el pipeline completo de forma autónoma sin pausas de confirmación manuales innecesarias.
   - `max_jobs_per_board` en `profile/pipeline_config.json` limita el máximo de vacantes a evaluar por consulta.
   - `delay_between_batches_seconds` y `delay_between_boards_seconds` aplican pausas configurables para prevenir bloqueos de cuota (`429`).

6. **IDs Canónicas y Deduplicación por Invariante**:
   - **Esquema de IDs**: IDs estables (`greenhouse_{board}_{id}`, `ashby_{company}_{id}`, `lever_{company}_{id}`, `exactas_{num}`, `linkedin_{id}` y hashes MD5 `manual_{md5(empresa:titulo)[:8]}`).
   - **Deduplicación por Invariante**: Vacantes ya guardadas en `jobs.json` son omitidas automáticamente antes de consumir slots de rankeo.

7. **Inspección Exhaustiva y Métodos de Postulación (`get_job_details`)**:
   - Recupera el detalle completo, justificación de fit, fortalezas, vacíos y el **link directo (`source_url`) junto con las instrucciones de postulación (`application_method`)** con fallback en 4 niveles.

8. **Soporte Multi-Idioma e Internacionalización Dinámica**:
   - Configurable en `profile/pipeline_config.json` (`"language": "es" | "en" | null`).
   - Si el idioma no está configurado, `jobbud_agent` pregunta al usuario y persiste su elección usando `set_language_preference`.
   - Reportes de telemetría y justificaciones de fit adaptados al idioma elegido.

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
│   ├── pipeline_config.json     # Límites del pipeline (idioma, cap por board, timers, exp máx)
│   ├── board_urls.json          # Registro persistente de tableros de empleo
│   ├── location_filters.json    # Países permitidos, ciudades/barrios y reglas remotas
│   ├── title_blacklist.md       # Términos excluidos en títulos (Pre-Parseo)
│   ├── department_blacklist.md  # Áreas excluidas en metadatos (Pre-Parseo)
│   ├── blacklist_roles.md       # Roles/áreas excluidas (Post-Parseo)
│   └── blacklist_seniority.md   # Seniorities excluidos (Post-Parseo)
└── src/
    ├── agent.py                 # Instancia principal de `jobbud_agent` (ADK Agent con 23 tools)
    ├── config.py                # Carga centralizada de variables de entorno (.env)
    ├── guidelines.md            # Instrucciones del sistema y directivas conversacionales
    ├── fetchers/                # Capa de Ingesta Unificada que retorna List[JobDict]
    │   ├── __init__.py          # Exporta funciones de fetcher y herramientas del agente
    │   ├── base.py              # Extractor de tecnologías y utilidades
    │   ├── greenhouse.py        # Conector API REST de Greenhouse (0 tokens LLM)
    │   ├── ashby.py             # Conector API REST de Ashby HQ (0 tokens LLM)
    │   ├── lever.py             # Conector API REST de Lever Public API (0 tokens LLM)
    │   ├── exactas.py           # Scraper FCEyN UBA + integración con parser
    │   ├── linkedin.py          # Extractor de avisos de LinkedIn + integración con parser
    │   └── manual.py            # Normalizador de texto crudo + integración con parser
    ├── subagents/
    │   ├── job_parser/          # Subagente extractor y estructurador (worker programático)
    │   │   ├── job_parser.py    # Definición de Agente ADK
    │   │   ├── guidelines.md    # Esquema de extracción y normalización
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
    └── tools/                   # Colección modular de 23 herramientas
        ├── __init__.py          # Exporta HERRAMIENTAS_BASICAS (las 23 herramientas)
        ├── queries.py           # Consultas, inspecciones detalladas y filtros deterministas
        ├── management.py        # Edición de estados, borrado, idioma, undo y herramientas de pipeline
        └── boards.py            # Registro y ordenamiento determinista de tableros
```

---

## 📐 Esquema y Contrato de Datos (`JobDict`)

Cada vacante procesada en JobBud se normaliza estrictamente bajo un diccionario unificado (`JobDict`) de **26 campos** antes de ser evaluada o persistida en `jobs.json`.

### 4.1. Especificación de Campos y Tipos

| Campo | Tipo | ¿Nulable? | Descripción y Valores Permitidos |
| :--- | :---: | :---: | :--- |
| `id` | `str` | No | Identificador único y determinista (ej. `greenhouse_invgate_4495272002`, `exactas_86_26`). |
| `created_at` | `str` | No | Timestamp ISO de ingestión en el sistema (ej. `2026-08-18T06:48:54.728087`). |
| `title` | `str` | No | Nombre del puesto limpio y normalizado. |
| `company` | `str` | No | Nombre de la empresa u organización contratante. |
| `location` | `str` | No | Ubicación geográfica normalizada (ej. `Buenos Aires, Argentina`, `Remote - US`). |
| `work_mode` | `str` | No | Modalidad de trabajo: `"Remoto"`, `"Híbrido"`, `"Presencial"` o `"Not specified"`. |
| `commitment` | `str` | No | Dedicación horaria: `"Full-time"`, `"Part-time"`, `"Contract"`, `"Internship"` o `"Not specified"`. |
| `department` | `str` | No | Área o departamento funcional (ej. `Engineering`, `Data`, `QA`, `Sales`). |
| `seniority` | `str` | No | Nivel de experiencia: `"Trainee"`, `"Junior"`, `"Semi-Senior"`, `"Senior"`, `"Lead / Executive"`. |
| `years_of_experience` | `int` | **Sí** | Años mínimos requeridos explícitos (entero numérico o `null` si no está especificado). |
| `salary_range` | `str` | **Sí** | Compensación o rango salarial publicado, o `null`. |
| `key_technologies` | `List[str]` | No | Array plano de tecnologías, stacks o herramientas principales requeridas. |
| `main_requirements` | `List[str]` | No | Array plano de requisitos y calificaciones clave del postulante. |
| `summary` | `str` | No | Resumen conciso del puesto en 2 o 3 oraciones. |
| `raw_text` | `str` | No | Texto íntegro y original de la publicación del empleo (preservado sin recortes). |
| `language` | `str` | No | Código de idioma detectado en el aviso original (`"es"` o `"en"`). |
| `source_page` | `str` | No | Nombre del portal de origen (ej. `Greenhouse`, `Ashby`, `Lever`, `Exactas UBA`, `LinkedIn`). |
| `source_url` | `str` | No | URL canónica directa a la publicación del empleo. |
| `application_method` | `str` | No | Instrucciones de postulación resueltas (link de postulación directa o correo electrónico de contacto). |
| `status` | `str` | No | Estado en el ciclo de vida: `"new"`, `"pending_ranking"`, `"ranked"`, `"disqualified"`, `"applied"`. |
| `score` | `int` | **Sí** | Puntaje de compatibilidad de 0 a 100 evaluado por el ranker (`null` si no está rankeada). |
| `justification` | `str` | **Sí** | Razón detallada y concisa del puntaje asignado redactada por el LLM ranker. |
| `strengths` | `List[str]` | No | Array plano de fortalezas y puntos de encaje detectados con el perfil del candidato. |
| `gaps` | `List[str]` | No | Array plano de brechas, habilidades faltantes o puntos de desajuste detectados. |
| `ranked_at` | `str` | **Sí** | Timestamp ISO del momento en que fue evaluada por `job_ranker_agent`, o `null`. |
| `user_notes` | `str` | **Sí** | Notas personalizadas ingresadas por el usuario, o `null`. |

### 4.2. Contrato de Fortalezas, Vacíos y Estados

* **Contrato Estricto para `strengths` y `gaps`**:
  ```json
  "strengths": ["string", "string"],
  "gaps": ["string", "string"]
  ```
  Está terminantemente prohibido almacenar objetos o diccionarios anidados (como `[{"text": "..."}]`). La función determinista `_normalize_string_list` garantiza en tiempo de ejecución que siempre sean listas planas `List[str]`.

* **Estados Válidos (`status`)**:
  - `"new"`: Vacante recién obtenida, aún en memoria.
  - `"pending_ranking"`: Vacante guardada en `jobs.json` sin evaluación LLM.
  - `"ranked"`: Vacante evaluada con score (0–100), justificación, fortalezas y vacíos.
  - `"applied"`: Vacante a la que el usuario ya se ha postulado.
  - `"disqualified"`: Vacante descartada manualmente por el usuario.

### 4.3. Esquema de IDs Estables por Plataforma

* **Greenhouse**: `greenhouse_{board_token}_{job_id}` (ej. `greenhouse_invgate_4495272002`).
* **Ashby HQ**: `ashby_{company}_{job_id}` (ej. `ashby_cursor_123456`).
* **Lever**: `lever_{company}_{job_id}` (ej. `lever_ryzlabs_abcd-1234`).
* **Exactas UBA**: `exactas_{num_part}` (ej. `exactas_86_26`).
* **LinkedIn**: `linkedin_{numeric_id}` (ej. `linkedin_4445031526`).
* **Texto Manual**: `manual_{md5(empresa:titulo)[:8]}` (ej. `manual_bebce99c`).

---

## 👤 Guía de Configuración Paso a Paso (`profile/`)

> **La arquitectura de JobBud es 100% agnóstica.** **NUNCA** tenés que modificar código fuente en Python (`src/`), ni las instrucciones de los agentes (`guidelines.md`).
> 
> **Para adaptar JobBud a tu propio perfil y carrera, únicamente tenés que completar los archivos dentro de la carpeta [`profile/`](profile/).**

A continuación se detalla cómo configurar cada archivo con ejemplos y plantillas listas para usar:

### 5.1. Paso 1: Tu Perfil Profesional (`candidate_profile.md`)
* **Ubicación**: [`profile/candidate_profile.md`](profile/candidate_profile.md)
* **Formato**: Markdown (`.md`)
* **Propósito**: Es el documento que lee `job_ranker_agent` para contrastar cada vacante.
* **Plantilla Recomendada**:
  ```markdown
  # Perfil Profesional del Candidato

  ## 🎓 Educación
  - **Carrera / Título**: Licenciatura en Ciencias de la Computación / Ingeniería en Sistemas
  - **Institución**: Universidad de Buenos Aires (UBA)
  - **Estado actual**: Estudiante avanzado (80% completado)

  ## 💼 Experiencia Laboral
  - **Desarrollador Junior** en Empresa X (2024 - Presente):
    - Desarrollo de APIs backend en Python (FastAPI) y bases de datos PostgreSQL.
    - Implementación de pipelines de CI/CD con Docker y GitHub Actions.

  ## 🛠️ Stack Tecnológico y Habilidades
  - **Lenguajes**: Python, C++, TypeScript, SQL.
  - **Frameworks & Herramientas**: FastAPI, React, Node.js, Docker, Git, Linux.

  ## 🌐 Idiomas
  - **Español**: Nativo.
  - **Inglés**: Avanzado / C1 (fluidez profesional para trabajo en remoto).

  ## 🎯 Preferencias de Búsqueda
  - Roles deseados: Backend Developer, Software Engineer Junior/Ssr, Data Engineer.
  - Modalidades aceptadas: Remoto o Híbrido en Buenos Aires.
  ```

### 5.2. Paso 2: Reglas y Política de Rankeo (`ranking_policy.md`)
* **Ubicación**: [`profile/ranking_policy.md`](profile/ranking_policy.md)
* **Formato**: Markdown (`.md`)
* **Propósito**: Define los criterios de puntuación (0 a 100) que el LLM ranker debe seguir.
* **Estructura**:
  - **Nivel 1 (Afinidad Técnica)**: Puntos por coincidencia de stack (+20 a +40).
  - **Nivel 2 (Nivel de Seniority)**: Ajuste al nivel del candidato (+10 a +20).
  - **Nivel 3 (Modalidad & Ubicación)**: Bonificación por modalidad preferida.
  - **Penalizaciones**: Descuento de puntos por requisitos faltantes o tecnologías no afines.

### 5.3. Paso 3: Parámetros del Motor (`pipeline_config.json`)
* **Ubicación**: [`profile/pipeline_config.json`](profile/pipeline_config.json)
* **Formato**: JSON
* **Ejemplo Completo**:
  ```json
  {
    "language": "es",
    "max_jobs_per_board": 5,
    "delay_between_batches_seconds": 3.0,
    "delay_between_boards_seconds": 10.0,
    "max_years_experience": 3,
    "auto_pipeline_execution": true
  }
  ```
* **Descripción de Propiedades**:
  - `"language"`: Idioma de los reportes y justificaciones (`"es"`, `"en"` o `null` para preguntar).
  - `"max_jobs_per_board"`: Límite máximo de vacantes nuevas a rankear por tablero (`null` para sin límite).
  - `"delay_between_batches_seconds"`: Pausa en segundos entre lotes de rankeo (evita rate limits `429`).
  - `"delay_between_boards_seconds"`: Pausa en segundos entre tableros en ejecuciones multitablero.
  - `"max_years_experience"`: Límite de años de experiencia requeridos (descarta vacantes con YOE mayor).
  - `"auto_pipeline_execution"`: `true` ejecuta el pipeline de 6 etapas automáticamente sin pausas innecesarias.

### 5.4. Paso 4: Filtros de Ubicación y Modalidad (`location_filters.json`)
* **Ubicación**: [`profile/location_filters.json`](profile/location_filters.json)
* **Formato**: JSON
* **Ejemplo Completo**:
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
        "CABA",
        "Capital Federal"
      ],
      "allowed_remote_regions": [
        "LATAM",
        "South America",
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

### 5.5. Paso 5: Listas Negras Pre y Post-Parseo (`*.md`)
* **Ubicación**:
  - Pre-Parseo (0 tokens): [`profile/title_blacklist.md`](profile/title_blacklist.md), [`profile/department_blacklist.md`](profile/department_blacklist.md)
  - Post-Parseo (0 tokens): [`profile/blacklist_roles.md`](profile/blacklist_roles.md), [`profile/blacklist_seniority.md`](profile/blacklist_seniority.md)
* **Formato**: Lista de viñetas en Markdown (`- Término`). Coincidencia insensible a mayúsculas y por palabra completa (`\bterm\b`).
* **Ejemplo (`profile/title_blacklist.md`)**:
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
* **Ejemplo (`profile/blacklist_seniority.md`)**:
  ```markdown
  # Seniority Blacklist
  - Senior
  - Lead
  - Staff
  - Principal
  - Director
  - Manager
  ```

### 5.6. Paso 6: Registro de Tableros (`board_urls.json`)
* **Ubicación**: [`profile/board_urls.json`](profile/board_urls.json)
* **Formato**: JSON (Administrable manualmente o mediante los comandos conversacionales `add_board_url` y `delete_board_url`).
* **Ejemplo**:
  ```json
  [
    {
      "id": "board_exactasuba",
      "name": "Exactas UBA",
      "url": "https://exactas.uba.ar/ofertas-de-trabajo-profesional/ofertas-activas-estudiantes/",
      "source_type": "exactas",
      "last_analyzed": null,
      "created_at": "2026-08-18T00:00:00",
      "notes": "Bolsa oficial FCEyN UBA"
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

## 🛠️ Suite de Herramientas (`HERRAMIENTAS_BASICAS`)

El agente orquestador maestro `jobbud_agent` interactúa exclusivamente a través de sus **23 herramientas modulares**:

| Dominio | Herramienta | Propósito |
| :--- | :--- | :--- |
| **Queries** | `check_existing_job` | Verifica deduplicación por ID, título o URL en `jobs.json`. |
| **Queries** | `get_job_raw_text` | Recupera el texto crudo completo original de una postulación. |
| **Queries** | `get_job_details` | Devuelve la ficha completa, justificación de fit y link directo de postulación. |
| **Queries** | `get_top_job_recommendations` | Lista el Top N mejores ofertas según puntaje de fit (excluyendo aplicadas/descartadas). |
| **Queries** | `list_jobs_by_status` | Lista empleos filtrados por estado (`ranked`, `applied`, `disqualified`). |
| **Queries** | `filter_jobs_by_blacklist` | Evalúa coincidencia contra listas negras de títulos y roles. |
| **Queries** | `filter_job_by_location` | Evalúa país, ciudad y modalidad contra `location_filters.json`. |
| **Management** | `mark_job_status` | Cambia el estado de una posición (`applied`, `disqualified`, `ranked`). |
| **Management** | `delete_job_from_json` | Elimina una posición de `jobs.json`. |
| **Management** | `revert_last_job_action` | Deshace el último cambio de estado o eliminación con backup automático. |
| **Management** | `execute_job_pipeline_tool` | Ejecuta el runner secuencial de filtrado y rankeo en lote para un tablero. |
| **Management** | `execute_multi_board_pipeline_tool` | Ejecuta el pipeline multitablero automático con timers y reporte Top 5. |
| **Management** | `set_language_preference` | Configura y persiste el idioma preferido (`es` / `en`) en `pipeline_config.json`. |
| **Management** | `get_language_preference` | Obtiene el idioma actualmente configurado en `pipeline_config.json`. |
| **Fetchers** | `fetch_greenhouse_job_content` | Consulta la API REST de portales Greenhouse (0 tokens LLM). |
| **Fetchers** | `fetch_ashby_job_content` | Consulta la API pública de portales Ashby HQ (0 tokens LLM). |
| **Fetchers** | `fetch_lever_job_content` | Consulta la API pública de portales Lever (0 tokens LLM). |
| **Fetchers** | `fetch_exactas_job_board` | Scrapea y normaliza avisos de la bolsa de empleo de Exactas UBA. |
| **Fetchers** | `fetch_linkedin_job_content` | Extrae contenido y normaliza publicaciones de LinkedIn. |
| **Boards** | `add_board_url` | Registra una nueva URL de tablero de empleo (`greenhouse`, `ashby`, `lever`, `exactas`). |
| **Boards** | `list_job_boards` | Lista todos los tableros ordenados de más antiguo/no analizado a más reciente. |
| **Boards** | `get_board_to_analyze` | Resuelve y analiza un tablero por su número o nombre actualizando `last_analyzed`. |
| **Boards** | `delete_board_url` | Elimina un tablero registrado por su número, ID o nombre. |

---

## 🚀 Instalación y Puesta en Marcha

### 7.1. Requisitos Previos e Instalación

* **Python 3.10** o superior.
* Clave de API de Google Gemini ([Google AI Studio](https://aistudio.google.com/)).

```bash
git clone https://github.com/usuario/jobbud.git
cd jobbud

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 7.2. Configurar Variables de Entorno (`.env`)

Crea o edita el archivo `.env` en la raíz del proyecto:

```env
GOOGLE_API_KEY=tu_api_key_de_google_gemini
DEFAULT_MODEL=gemini-3.1-flash-lite
ADK_DEFAULT_APP_NAME=src
```

### 7.3. Modos de Ejecución (CLI vs Web ADK)

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

* **Listar y Consultar Tableros**:
  > *"mis boards"* o *"listar tableros"*
* **Analizar un Tablero Específico**:
  > *"analizá el board 1"* o *"analizar InvGate"*
* **Ejecutar Búsqueda Multitablero Automática**:
  > *"analizá todos mis tableros"* o *"analizá los tableros no revisados este mes"*
* **Ver Detalles y Método de Postulación Directo**:
  > *"dame los detalles de la vacante greenhouse_invgate_4495272002"* o *"cómo me postulo a la vacante de Neix?"*
* **Ver Mejores Recomendaciones Acumuladas**:
  > *"mostrame el top 5 para postularme"*
* **Gestionar Estados de Postulación**:
  > *"marcar la vacante X como aplicada"* o *"descartar la vacante Y"*
* **Deshacer Última Acción**:
  > *"deshacer"* o *"revertir"*
* **Agregar un Nuevo Tablero**:
  > *"agregá el tablero de Ashby de Linear: https://jobs.ashbyhq.com/linear"*

---

## 🛡️ Integridad de Datos y Persistencia

1. **Deduplicación Automática en 3 Niveles**:
   - Antes de parsear o rankear, el sistema verifica por ID, URL y título si la vacante ya existe en `jobs.json`, ahorrando el 100% de tokens LLM en posiciones ya conocidas.
2. **Inmutabilidad de Datos de Origen**:
   - Durante la evaluación y rankeo, los datos extraídos de la publicación original (`title`, `company`, `location`, `raw_text`, `source_url`) se preservan intactos, actualizando únicamente los campos de análisis (`score`, `justification`, `strengths`, `gaps`, `status`).
3. **Mecanismo de Respaldo y Reversibilidad (`revert_last_job_action`)**:
   - Cualquier cambio de estado (`applied`, `disqualified`) o eliminación genera un respaldo automático en `.last_job_action_backup.json`, permitiendo al usuario deshacer la acción de forma instantánea.
