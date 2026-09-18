from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.schemas.resume import (
    ResumeCreate,
    ResumeRead,
    ResumeTextRead,
    ResumeUploadResponse,
)
from backend.schemas.resume_analysis import ResumeAnalysisRead
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

router = APIRouter(prefix="/resumes")


@router.get(
    "",
    response_model=list[ResumeRead],
    summary="List resumes",
    description="Returns resume metadata records.",
)
def read_resumes(db: Session = Depends(get_db)) -> list[ResumeRead]:
    resumes = list_resumes(db)
    return [ResumeRead.model_validate(item) for item in resumes]


@router.get(
    "/{resume_id}",
    response_model=ResumeRead,
    summary="Get resume",
    description="Returns one resume metadata record by id.",
)
def read_resume(resume_id: int, db: Session = Depends(get_db)) -> ResumeRead:
    resume = get_resume(db, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found"
        )
    return ResumeRead.model_validate(resume)


@router.post(
    "",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create resume metadata",
    description="Creates a resume metadata record without parsing file contents.",
)
def create_resume_endpoint(
    payload: ResumeCreate,
    db: Session = Depends(get_db),
) -> ResumeRead:
    try:
        resume = create_resume(db, payload)
    except ResumeServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ResumeRead.model_validate(resume)


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and parse resume",
    description="Validates, stores, parses, and persists resume metadata and text.",
)
def upload_resume_endpoint(
    profile_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ResumeUploadResponse:
    try:
        resume = upload_resume(db, profile_id=profile_id, file=file)
    except ResumeServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    normalized_text = resume.normalized_text or ""
    return ResumeUploadResponse(
        id=resume.id,
        profile_id=resume.profile_id,
        name=resume.name,
        file_type=resume.file_type,
        mime_type=resume.mime_type,
        file_size_bytes=resume.file_size_bytes,
        page_count=resume.page_count,
        parse_status=resume.parse_status,
        text_preview=normalized_text[:1000],
        text_length=len(normalized_text),
        created_at=resume.created_at,
    )


@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete resume metadata",
    description="Deletes a resume metadata record.",
)
def delete_resume_endpoint(resume_id: int, db: Session = Depends(get_db)) -> None:
    resume = get_resume(db, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found"
        )

    delete_resume(db, resume)


@router.get(
    "/{resume_id}/text",
    response_model=ResumeTextRead,
    summary="Get parsed resume text",
    description="Returns normalized extracted text for a resume.",
)
def read_resume_text(resume_id: int, db: Session = Depends(get_db)) -> ResumeTextRead:
    resume = get_resume_text(db, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found"
        )

    if not resume.normalized_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed resume text not found",
        )

    return ResumeTextRead(
        id=resume.id,
        name=resume.name,
        file_type=resume.file_type,
        page_count=resume.page_count,
        normalized_text=resume.normalized_text,
    )


@router.post(
    "/{resume_id}/analyze",
    response_model=ResumeAnalysisRead,
    summary="Analyze resume with AI",
    description=(
        "Runs Ollama-based extraction from parsed resume text and persists the "
        "structured result."
    ),
)
def analyze_resume_endpoint(
    resume_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
) -> ResumeAnalysisRead:
    try:
        resume, profile = analyze_resume(db, resume_id=resume_id, force=force)
    except ResumeAnalysisServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ResumeAnalysisRead(
        resume_id=resume.id,
        analysis_status=resume.analysis_status,
        analyzed_at=resume.analyzed_at,
        profile=profile,
    )


@router.get(
    "/{resume_id}/analysis",
    response_model=ResumeAnalysisRead,
    summary="Get latest resume analysis",
    description="Returns the latest persisted AI analysis for a resume.",
)
def read_resume_analysis(
    resume_id: int,
    db: Session = Depends(get_db),
) -> ResumeAnalysisRead:
    try:
        resume, profile = get_resume_analysis(db, resume_id=resume_id)
    except ResumeAnalysisServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ResumeAnalysisRead(
        resume_id=resume.id,
        analysis_status=resume.analysis_status,
        analyzed_at=resume.analyzed_at,
        profile=profile,
    )
