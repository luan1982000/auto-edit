"""Job status endpoints used by the polling UI."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db import get_session
from app.models import Job
from app.schemas import JobRead

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    status: str | None = Query(default=None),
    video_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[Job]:
    statement = select(Job)
    if status:
        statement = statement.where(Job.status == status)
    if video_id:
        statement = statement.where(Job.video_id == video_id)
    statement = statement.order_by(Job.created_at.desc()).limit(limit)
    return list(session.exec(statement).all())


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(get_session)) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    return job
