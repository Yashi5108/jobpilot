from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import UserProfile
from backend.schemas.profile import ProfileCreate, ProfileUpdate


def get_profile(db: Session) -> UserProfile | None:
    return db.scalar(select(UserProfile).order_by(UserProfile.id.asc()).limit(1))


def create_profile(db: Session, payload: ProfileCreate) -> UserProfile:
    profile = UserProfile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    profile: UserProfile,
    payload: ProfileUpdate,
) -> UserProfile:
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(profile, field_name, value)

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
