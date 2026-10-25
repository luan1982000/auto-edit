"""Application settings (single-row table) and logo upload."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.config import AppConfig
from app.db import get_session
from app.models import AppSettings
from app.schemas import SettingsRead, SettingsUpdate
from app.services.assets import (
    IMAGE_TYPES,
    MAX_LOGO_BYTES,
    delete_logo_files,
    resolve_logo,
    save_logo,
)
from app.settings_store import get_or_create_settings

router = APIRouter(prefix="/api", tags=["settings"])


def _config(request: Request) -> AppConfig:
    return request.app.state.config


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


@router.post("/settings/logo", response_model=SettingsRead)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> AppSettings:
    contents = await file.read(MAX_LOGO_BYTES + 1)
    if len(contents) > MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Logo quá lớn — tối đa {MAX_LOGO_BYTES // (1024 * 1024)} MB",
        )
    try:
        path = save_logo(_config(request), contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_or_create_settings(session)
    settings.logo_path = str(path)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


@router.get("/settings/logo")
def read_logo(
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    settings = get_or_create_settings(session)
    path = resolve_logo(_config(request), settings.logo_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Chưa upload logo")
    media_type = IMAGE_TYPES.get(Path(path).suffix.lstrip(".").lower(), "image/png")
    return FileResponse(path, media_type=media_type)


@router.delete("/settings/logo", response_model=SettingsRead)
def remove_logo(
    request: Request,
    session: Session = Depends(get_session),
) -> AppSettings:
    settings = get_or_create_settings(session)
    settings.logo_path = ""
    session.add(settings)
    session.commit()
    session.refresh(settings)
    delete_logo_files(_config(request))
    return settings
