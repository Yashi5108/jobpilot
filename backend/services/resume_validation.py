from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path


class ResumeValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
}


@dataclass(frozen=True)
class ValidatedResumeUpload:
    original_filename: str
    extension: str
    mime_type: str
    size_bytes: int


def validate_resume_upload(
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_size_bytes: int,
) -> ValidatedResumeUpload:
    if not filename:
        raise ResumeValidationError("Filename is required")

    if len(content) == 0:
        raise ResumeValidationError("Uploaded file is empty")

    if len(content) > max_size_bytes:
        raise ResumeValidationError(
            f"File exceeds maximum allowed size of {max_size_bytes} bytes",
            status_code=413,
        )

    candidate_name = Path(filename).name
    if candidate_name != filename:
        raise ResumeValidationError("Unsafe filename: path separators are not allowed")

    if candidate_name in {".", ".."}:
        raise ResumeValidationError("Unsafe filename")

    extension = Path(candidate_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ResumeValidationError(
            "Unsupported file type. Please upload a PDF or DOCX resume.",
            status_code=415,
        )

    inferred_mime = _infer_mime(extension, content)
    if content_type:
        normalized = content_type.lower().strip()
        allowed_mimes = ALLOWED_MIME_TYPES.get(extension, set())
        if normalized not in allowed_mimes and normalized != inferred_mime:
            raise ResumeValidationError(
                "Uploaded file content does not match declared content type.",
                status_code=415,
            )

    return ValidatedResumeUpload(
        original_filename=candidate_name,
        extension=extension,
        mime_type=inferred_mime,
        size_bytes=len(content),
    )


def _infer_mime(extension: str, content: bytes) -> str:
    if extension == ".pdf":
        if not content.startswith(b"%PDF"):
            raise ResumeValidationError(
                "Invalid PDF file signature.",
                status_code=415,
            )
        return "application/pdf"

    if extension == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise ResumeValidationError(
                "Invalid DOCX container.",
                status_code=415,
            ) from exc

        required_entries = {"[Content_Types].xml", "word/document.xml"}
        if not required_entries.issubset(names):
            raise ResumeValidationError(
                "Invalid DOCX structure.",
                status_code=415,
            )
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    raise ResumeValidationError("Unsupported file extension", status_code=415)
