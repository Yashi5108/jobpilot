from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.schemas.job import JobCreate, JobRead, JobUpdate
from backend.schemas.job_analysis import JobAnalysisRead
from backend.schemas.job_discovery import JobDiscoveryRequest, JobDiscoveryResponse
from backend.schemas.job_import import JobImportResult, ManualJobImportRequest
from backend.schemas.job_match import JobMatchRequest, JobMatchResult
from backend.services.job_analysis_service import (
    JobAnalysisServiceError,
    analyze_job,
    get_job_analysis,
)
from backend.services.job_discovery.service import (
    JobDiscoveryServiceError,
    discover_jobs_for_resume,
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

router = APIRouter(prefix="/jobs")


@router.get(
    "",
    response_model=list[JobRead],
    summary="List jobs",
    description="Returns manually tracked jobs from the local database.",
)
def read_jobs_filtered(
    company: str | None = None,
    db: Session = Depends(get_db),
) -> list[JobRead]:
    jobs = list_jobs(db, company=company)
    return [JobRead.model_validate(item) for item in jobs]


@router.get("/{job_id}", response_model=JobRead, summary="Get job")
def read_job_by_id(job_id: int, db: Session = Depends(get_db)) -> JobRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return JobRead.model_validate(job)


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create job",
    description="Creates a job entry for manual insertion workflows.",
)
def create_job_endpoint(payload: JobCreate, db: Session = Depends(get_db)) -> JobRead:
    try:
        job = create_job(db, payload)
    except JobServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return JobRead.model_validate(job)


@router.post(
    "/discover",
    response_model=JobDiscoveryResponse,
    summary="Discover jobs for a resume",
    description=(
        "Builds search criteria from analyzed resume data, discovers jobs from "
        "supported sources, analyzes them, and returns best matches."
    ),
)
def discover_jobs_endpoint(
    payload: JobDiscoveryRequest,
    db: Session = Depends(get_db),
) -> JobDiscoveryResponse:
    try:
        return discover_jobs_for_resume(db, payload)
    except JobDiscoveryServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/import/manual",
    response_model=JobImportResult,
    summary="Import one manual job",
    description="Normalizes and imports one manual job record through connector flow.",
)
def import_manual_job_endpoint(
    payload: ManualJobImportRequest,
    db: Session = Depends(get_db),
) -> JobImportResult:
    try:
        return import_manual_job(db, payload)
    except JobImportServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/import/json",
    response_model=JobImportResult,
    summary="Import jobs from JSON",
    description="Imports a local JSON file containing an array of normalized jobs.",
)
def import_jobs_json_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobImportResult:
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=422, detail="Please upload a .json file")

    content = file.file.read()
    try:
        return import_jobs_from_json(db, content)
    except JobImportServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/import/csv",
    response_model=JobImportResult,
    summary="Import jobs from CSV",
    description="Imports a local CSV file containing normalized job columns.",
)
def import_jobs_csv_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Please upload a .csv file")

    content = file.file.read()
    try:
        return import_jobs_from_csv(db, content)
    except JobImportServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.put(
    "/{job_id}",
    response_model=JobRead,
    summary="Update job",
    description="Updates a manually entered job record.",
)
def update_job_endpoint(
    job_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
) -> JobRead:
    try:
        job = update_job(db, job_id=job_id, payload=payload)
    except JobServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return JobRead.model_validate(job)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete job",
    description="Deletes a job record when no application history is linked.",
)
def delete_job_endpoint(job_id: int, db: Session = Depends(get_db)) -> None:
    try:
        delete_job(db, job_id=job_id)
    except JobServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/{job_id}/analyze",
    response_model=JobAnalysisRead,
    summary="Analyze job with AI",
    description=(
        "Runs Ollama-based extraction from stored job description and persists "
        "the structured result."
    ),
)
def analyze_job_endpoint(
    job_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
) -> JobAnalysisRead:
    try:
        job, analysis = analyze_job(db, job_id=job_id, force=force)
    except JobAnalysisServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return JobAnalysisRead(
        job_id=job.id,
        analysis_status=job.analysis_status,
        analyzed_at=job.analyzed_at,
        analysis=analysis,
    )


@router.get(
    "/{job_id}/analysis",
    response_model=JobAnalysisRead,
    summary="Get latest job analysis",
    description="Returns the latest persisted AI analysis for a job.",
)
def read_job_analysis(
    job_id: int,
    db: Session = Depends(get_db),
) -> JobAnalysisRead:
    try:
        job, analysis = get_job_analysis(db, job_id=job_id)
    except JobAnalysisServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return JobAnalysisRead(
        job_id=job.id,
        analysis_status=job.analysis_status,
        analyzed_at=job.analyzed_at,
        analysis=analysis,
    )


@router.post(
    "/{job_id}/match",
    response_model=JobMatchResult,
    summary="Match job with resume",
    description=(
        "Deterministically compares stored resume analysis and job analysis, "
        "persists the result, and returns a structured breakdown."
    ),
)
def match_job_endpoint(
    job_id: int,
    payload: JobMatchRequest,
    db: Session = Depends(get_db),
) -> JobMatchResult:
    try:
        return match_job_with_resume(db, job_id=job_id, resume_id=payload.resume_id)
    except MatchingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/{job_id}/matches",
    response_model=list[JobMatchResult],
    summary="List job matches",
    description="Returns persisted deterministic match results for a job.",
)
def read_job_matches(
    job_id: int,
    db: Session = Depends(get_db),
) -> list[JobMatchResult]:
    try:
        return get_job_matches(db, job_id=job_id)
    except MatchingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/{job_id}/matches/{resume_id}",
    response_model=JobMatchResult,
    summary="Get job match for resume",
    description="Returns one persisted match result for a specific resume and job.",
)
def read_job_match_for_resume(
    job_id: int,
    resume_id: int,
    db: Session = Depends(get_db),
) -> JobMatchResult:
    try:
        return get_job_match_for_resume(db, job_id=job_id, resume_id=resume_id)
    except MatchingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
