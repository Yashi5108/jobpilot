from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.browser.assistant import (
    BrowserAssistantServiceError,
    run_browser_assistant,
)
from backend.browser.mapping import BrowserField
from backend.database.database import get_db
from backend.database.models import ApplicationStatus
from backend.schemas.application import (
    ApplicationApproveAction,
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationSubmitAction,
)
from backend.schemas.application_execution import (
    ApplicationExecutionRequest,
    ApplicationExecutionResponse,
)
from backend.schemas.application_preparation import (
    ApplicationPreparationRead,
    ApplicationReviewRead,
    ApplicationReviewUpdateRequest,
    PrepareApplicationRequest,
)
from backend.schemas.application_tracker import ApplicationTrackerItem
from backend.schemas.browser_assistant import (
    BrowserAssistRequest,
    BrowserAssistResponse,
)
from backend.services.application_execution_service import (
    ApplicationExecutionServiceError,
    execute_application,
)
from backend.services.application_preparation_service import (
    ApplicationPreparationServiceError,
    get_application_review,
    prepare_application,
    regenerate_cover_letter,
    update_application_review,
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

router = APIRouter(prefix="/applications")


@router.get(
    "",
    response_model=list[ApplicationRead],
    summary="List applications",
    description="Returns all application tracking records.",
)
def read_applications(db: Session = Depends(get_db)) -> list[ApplicationRead]:
    applications = list_applications(db)
    return [ApplicationRead.model_validate(item) for item in applications]


@router.post(
    "",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create application",
    description="Creates a new application tracking record.",
)
def create_application_endpoint(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    try:
        application = create_application(db, payload)
    except ApplicationServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    return ApplicationRead.model_validate(application)


@router.patch(
    "/{application_id}/status",
    response_model=ApplicationRead,
    summary="Update application status",
    description="Updates status for an existing application.",
)
def update_application_status_endpoint(
    application_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    application = get_application(db, application_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    try:
        updated = update_application_status(db, application, payload.status)
    except ApplicationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ApplicationRead.model_validate(updated)


@router.get(
    "/tracker",
    response_model=list[ApplicationTrackerItem],
    summary="Application tracker",
    description="Returns enriched application tracker rows with timeline events.",
)
def read_application_tracker(
    status: ApplicationStatus | None = None,
    company: str | None = None,
    db: Session = Depends(get_db),
) -> list[ApplicationTrackerItem]:
    return list_application_tracker_items(db, status=status, company=company)


@router.post(
    "/prepare",
    response_model=ApplicationPreparationRead,
    summary="Prepare application",
    description="Generates cover letter and screening drafts for one job/resume pair.",
)
def prepare_application_endpoint(
    payload: PrepareApplicationRequest,
    db: Session = Depends(get_db),
) -> ApplicationPreparationRead:
    try:
        return prepare_application(db, payload)
    except ApplicationPreparationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/{application_id}/review",
    response_model=ApplicationReviewRead,
    summary="Get application review",
    description="Returns the full review payload required before manual submission.",
)
def read_application_review(
    application_id: int,
    db: Session = Depends(get_db),
) -> ApplicationReviewRead:
    try:
        return get_application_review(db, application_id)
    except ApplicationPreparationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.patch(
    "/{application_id}/review",
    response_model=ApplicationReviewRead,
    summary="Update application review",
    description=(
        "Persists user edits and review statuses for cover letter and "
        "screening answers."
    ),
)
def update_application_review_endpoint(
    application_id: int,
    payload: ApplicationReviewUpdateRequest,
    db: Session = Depends(get_db),
) -> ApplicationReviewRead:
    try:
        return update_application_review(db, application_id, payload)
    except ApplicationPreparationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/{application_id}/cover-letter/regenerate",
    response_model=ApplicationReviewRead,
    summary="Regenerate cover letter",
)
def regenerate_cover_letter_endpoint(
    application_id: int,
    db: Session = Depends(get_db),
) -> ApplicationReviewRead:
    try:
        return regenerate_cover_letter(db, application_id)
    except ApplicationPreparationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/{application_id}/approve",
    response_model=ApplicationRead,
    summary="Approve application for submission",
)
def approve_application_endpoint(
    application_id: int,
    payload: ApplicationApproveAction,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    if not payload.approve:
        raise HTTPException(status_code=422, detail="approve must be true")

    application = get_application(db, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        updated = approve_application_review(db, application)
    except ApplicationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApplicationRead.model_validate(updated)


@router.post(
    "/{application_id}/submit-confirmation",
    response_model=ApplicationRead,
    summary="Confirm manual submission",
)
def confirm_submission_endpoint(
    application_id: int,
    payload: ApplicationSubmitAction,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="confirm must be true")

    application = get_application(db, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        updated = confirm_application_submitted(db, application)
    except ApplicationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ApplicationRead.model_validate(updated)


@router.post(
    "/{application_id}/execute",
    response_model=ApplicationExecutionResponse,
    summary="Execute application",
    description=(
        "Uses an authorized API submission when supported, otherwise runs a "
        "browser-assisted fill or returns OPEN_AND_APPLY."
    ),
)
def execute_application_endpoint(
    application_id: int,
    payload: ApplicationExecutionRequest,
    db: Session = Depends(get_db),
) -> ApplicationExecutionResponse:
    try:
        return execute_application(db, application_id, payload)
    except ApplicationExecutionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/{application_id}/browser-assist",
    response_model=BrowserAssistResponse,
    summary="Run browser assistant",
    description=(
        "Maps and optionally fills known fields in a job application form. "
        "Never auto-submits."
    ),
)
def run_browser_assist_endpoint(
    application_id: int,
    payload: BrowserAssistRequest,
    db: Session = Depends(get_db),
) -> BrowserAssistResponse:
    try:
        fields = [
            BrowserField(
                name=item.name,
                label=item.label,
                field_type=item.field_type,
                required=item.required,
            )
            for item in payload.fields
        ]
        mapped, unknown, message = run_browser_assistant(
            db=db,
            application_id=application_id,
            application_url=payload.application_url,
            fields=fields,
            dry_run=payload.dry_run,
        )
    except BrowserAssistantServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return BrowserAssistResponse(
        application_id=application_id,
        dry_run=payload.dry_run,
        mapped_fields=mapped,
        unknown_fields=unknown,
        message=message,
    )


@router.get(
    "/{application_id}",
    response_model=ApplicationRead,
    summary="Get application",
    description="Returns one application record by id.",
)
def read_application(
    application_id: int,
    db: Session = Depends(get_db),
) -> ApplicationRead:
    application = get_application(db, application_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return ApplicationRead.model_validate(application)
