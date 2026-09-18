from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate
from backend.services.profile_service import create_profile, get_profile, update_profile

router = APIRouter(prefix="/profile")


@router.get(
    "",
    response_model=ProfileRead,
    summary="Get user profile",
    description="Returns the current local user profile.",
)
def read_profile(db: Session = Depends(get_db)) -> ProfileRead:
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    return ProfileRead.model_validate(profile)


@router.post(
    "",
    response_model=ProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user profile",
    description="Creates a profile for local single-user usage.",
)
def create_profile_endpoint(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
) -> ProfileRead:
    profile = create_profile(db, payload)
    return ProfileRead.model_validate(profile)


@router.put(
    "",
    response_model=ProfileRead,
    summary="Update user profile",
    description="Updates the current local user profile.",
)
def update_profile_endpoint(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
) -> ProfileRead:
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )

    updated_profile = update_profile(db, profile, payload)
    return ProfileRead.model_validate(updated_profile)
