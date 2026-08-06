"""
JobBud Tools Package.

Consolidates and exports all basic tools as HERRAMIENTAS_BASICAS.
"""

from src.tools.fetchers import (
    fetch_exactas_job_board,
    fetch_linkedin_job_content,
    fetch_greenhouse_job_content
)
from src.tools.queries import (
    check_existing_job,
    get_job_raw_text,
    get_job_details,
    get_top_job_recommendations,
    list_jobs_by_status,
    filter_jobs_by_blacklist,
    filter_job_by_location
)
from src.tools.management import (
    mark_job_status,
    delete_job_from_json,
    revert_last_job_action,
    execute_job_pipeline_tool
)
from src.tools.boards import (
    add_board_url,
    list_job_boards,
    get_board_to_analyze,
    delete_board_url
)

HERRAMIENTAS_BASICAS = [
    check_existing_job,
    get_job_raw_text,
    get_job_details,
    get_top_job_recommendations,
    list_jobs_by_status,
    filter_jobs_by_blacklist,
    filter_job_by_location,
    mark_job_status,
    delete_job_from_json,
    revert_last_job_action,
    execute_job_pipeline_tool,
    fetch_linkedin_job_content,
    fetch_exactas_job_board,
    fetch_greenhouse_job_content,
    add_board_url,
    list_job_boards,
    get_board_to_analyze,
    delete_board_url
]






