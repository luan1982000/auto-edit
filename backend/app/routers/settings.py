"""Application settings (single-row table)."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.models import AppSettings
from app.schemas import SettingsRead, SettingsUpdate
from app.settings_store import get_or_create_settings

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsRead)
def read_settings(session: Session = Depends(get_session)) -> AppSettings:
    return get_or_create_settings(session)


@router.put("/settings", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate,
    session: Session = Depends(get_session),
) -> AppSettings:
    settings = get_or_create_settings(session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings
