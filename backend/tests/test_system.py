import subprocess
import sys
from pathlib import Path

from app.routers.system import tool_status


def test_tool_status_tolerates_missing_ytdlp(monkeypatch) -> None:
    import importlib

    import app.routers.system as system

    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "yt_dlp":
            raise ImportError("No module named 'yt_dlp'")
        return real_import(name, package)

    monkeypatch.setattr(system.importlib, "import_module", fake_import)

    status = tool_status()

    assert status["yt_dlp"] is False
    assert status["yt_dlp_version"] is None


def test_app_imports_and_health_works_without_ytdlp(tmp_path: Path) -> None:
    script = f"""
import sys

class BlockYtDlp:
    def find_spec(self, name, path=None, target=None):
        if name == "yt_dlp" or name.startswith("yt_dlp."):
            raise ModuleNotFoundError("blocked for test")
        return None

sys.meta_path.insert(0, BlockYtDlp())

from fastapi.testclient import TestClient
from app.config import AppConfig
from app.main import create_app

config = AppConfig(data_dir={str(tmp_path / "data")!r}, _env_file=None)
app = create_app(config, start_worker=False)
with TestClient(app) as client:
    payload = client.get("/api/health").json()
    assert payload["yt_dlp"] is False
    assert payload["yt_dlp_version"] is None
    assert "Thiếu yt-dlp" in " ".join(payload["problems"])
    assert client.get("/api/videos").status_code == 200
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")
