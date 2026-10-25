"""System status endpoints (tool availability, later yt-dlp updates)."""

import importlib.util
import shutil

import yt_dlp
from fastapi import APIRouter

from app.services.updater import run_update

router = APIRouter(prefix="/api", tags=["system"])


def tool_status() -> dict[str, object]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    yt_dlp_available = importlib.util.find_spec("yt_dlp") is not None
    return {
        "ffmpeg": ffmpeg is not None,
        "ffprobe": ffprobe is not None,
        "yt_dlp": yt_dlp_available,
        "yt_dlp_version": yt_dlp.version.__version__ if yt_dlp_available else None,
    }


@router.get("/health")
def health() -> dict[str, object]:
    status = tool_status()
    problems: list[str] = []
    for tool in ("ffmpeg", "ffprobe"):
        if not status[tool]:
            problems.append(f"Thiếu {tool} trong PATH — video sẽ không xử lý được")
    if not status["yt_dlp"]:
        problems.append("Thiếu yt-dlp — không tải được video")
    return {"ok": True, **status, "problems": problems}


@router.post("/system/update-ytdlp")
def update_ytdlp() -> dict[str, object]:
    """Run `python -m pip install --upgrade yt-dlp` in this environment."""
    result = run_update()
    return {
        "ok": result.ok,
        "output": result.output,
        "version": result.version,
        "restart_required": result.restart_required,
    }
