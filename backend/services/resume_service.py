from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database.models import Resume, UserProfile
from backend.schemas.resume import ResumeCreate
from backend.services.resume_parser import ResumeParseError, parse_resume
from backend.services.resume_validation import (
    ResumeValidationError,
    validate_resume_upload,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ResumeServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def list_resumes(db: Session) -> list[Resume]:
    return list(db.scalars(select(Resume).order_by(Resume.id.asc())).all())


def get_resume(db: Session, resume_id: int) -> Resume | None:
    return db.get(Resume, resume_id)


def create_resume(db: Session, payload: ResumeCreate) -> Resume:
    profile = db.get(UserProfile, payload.profile_id)
    if profile is None:
        raise ResumeServiceError("Profile not found", status_code=404)

    resume = Resume(**payload.model_dump())
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def upload_resume(db: Session, profile_id: int, file: UploadFile) -> Resume:
    profile = db.get(UserProfile, profile_id)
    if profile is None:
        raise ResumeServiceError("Profile not found", status_code=404)

    payload = file.file.read()
    settings = get_settings()

    try:
        validated = validate_resume_upload(
            filename=file.filename,
            content_type=file.content_type,
            content=payload,
            max_size_bytes=settings.resume_upload_max_bytes,
        )
    except ResumeValidationError as exc:
        raise ResumeServiceError(str(exc), status_code=exc.status_code) from exc

    storage_path = _save_resume_file(payload, validated.extension)

    try:
        parsed = parse_resume(
            file_path=storage_path,
            file_type=validated.extension,
            filename=validated.original_filename,
        )
    except ResumeParseError as exc:
        storage_path.unlink(missing_ok=True)
        raise ResumeServiceError(str(exc), status_code=422) from exc

    resume = Resume(
        profile_id=profile_id,
        name=validated.original_filename,
        file_path=_display_file_path(storage_path),
        file_type=parsed.file_type,
        mime_type=validated.mime_type,
        file_size_bytes=validated.size_bytes,
        page_count=parsed.page_count,
        parse_status="PARSED",
        raw_text=parsed.raw_text,
        normalized_text=parsed.normalized_text,
        analysis_status="NOT_ANALYZED",
        analysis_result=None,
        analyzed_at=None,
        is_default=False,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def delete_resume(db: Session, resume: Resume) -> None:
    _delete_stored_resume_file(resume.file_path)
    db.delete(resume)
    db.commit()


def get_resume_text(db: Session, resume_id: int) -> Resume | None:
    return db.get(Resume, resume_id)


def _save_resume_file(content: bytes, extension: str) -> Path:
    storage_dir = _resolve_storage_dir(get_settings().resume_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    destination = storage_dir / filename
    destination.write_bytes(content)
    return destination.resolve()


def _display_file_path(storage_path: Path) -> str:
    cwd = Path.cwd().resolve()
    try:
        return str(storage_path.relative_to(cwd))
    except ValueError:
        return str(storage_path)


def _delete_stored_resume_file(stored_path: str) -> None:
    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    storage_root = _resolve_storage_dir(get_settings().resume_storage_dir)
    if not candidate.is_relative_to(storage_root):
        return

    candidate.unlink(missing_ok=True)


def _resolve_storage_dir(path_value: str) -> Path:
    storage_dir = Path(path_value)
    if not storage_dir.is_absolute():
        storage_dir = (PROJECT_ROOT / storage_dir).resolve()
    return storage_dir
