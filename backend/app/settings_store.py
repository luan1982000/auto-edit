from sqlmodel import Session

from app.models import AppSettings


def get_or_create_settings(session: Session) -> AppSettings:
    """Settings live in a single row with id=1."""
    settings = session.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings
