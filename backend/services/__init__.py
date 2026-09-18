"""Service layer for JobPilot backend."""

from backend.services.analytics_service import get_analytics_overview
from backend.services.application_preparation_service import (
    ApplicationPreparationServiceError,
    get_application_review,
    prepare_application,
    regenerate_cover_letter,
)
from backend.services.application_service import (
    ApplicationServiceError,
    approve_application_review,
    confirm_application_submitted,
    create_application,
    get_application,
    list_application_tracker_items,
    list_applications,
    update_application_status,
)
from backend.services.job_analysis_service import (
    JobAnalysisServiceError,
    analyze_job,
    get_job_analysis,
)
from backend.services.job_import_service import (
    JobImportServiceError,
    import_jobs_from_csv,
    import_jobs_from_json,
    import_manual_job,
)
from backend.services.job_service import (
    JobServiceError,
    create_job,
    delete_job,
    get_job,
    list_jobs,
    update_job,
)
from backend.services.matching_service import (
    MatchingServiceError,
    get_job_match_for_resume,
    get_job_matches,
    match_job_with_resume,
)
from backend.services.profile_service import create_profile, get_profile, update_profile
from backend.services.resume_analysis_service import (
    ResumeAnalysisServiceError,
    analyze_resume,
    get_resume_analysis,
)
from backend.services.resume_service import (
    ResumeServiceError,
    create_resume,
    delete_resume,
    get_resume,
    get_resume_text,
    list_resumes,
    upload_resume,
)

__all__ = [
    "create_application",
    "get_application",
    "list_applications",
    "list_application_tracker_items",
    "update_application_status",
    "approve_application_review",
    "confirm_application_submitted",
    "ApplicationServiceError",
    "prepare_application",
    "get_application_review",
    "regenerate_cover_letter",
    "ApplicationPreparationServiceError",
    "get_analytics_overview",
    "create_job",
    "delete_job",
    "get_job",
    "analyze_job",
    "get_job_analysis",
    "JobAnalysisServiceError",
    "import_manual_job",
    "import_jobs_from_json",
    "import_jobs_from_csv",
    "JobImportServiceError",
    "match_job_with_resume",
    "get_job_matches",
    "get_job_match_for_resume",
    "MatchingServiceError",
    "list_jobs",
    "update_job",
    "JobServiceError",
    "create_profile",
    "get_profile",
    "update_profile",
    "create_resume",
    "delete_resume",
    "get_resume",
    "get_resume_text",
    "list_resumes",
    "upload_resume",
    "ResumeServiceError",
    "ResumeAnalysisServiceError",
    "analyze_resume",
    "get_resume_analysis",
]
