# Phase 1 — Skeleton + Download + List

- **Commit:** `d5e8b5b` (base `c4e28cf`)
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng
- **Tài liệu phase sau:** [phase-2.md](phase-2.md)

## Phạm vi đã làm

- Khởi tạo backend FastAPI + SQLite, kiểm tra `ffmpeg`/`ffprobe`/`yt-dlp` lúc startup.
- Worker thread đọc job `pending`, chạy và cập nhật tiến độ vào bảng `jobs`.
- Tải video bằng thư viện yt-dlp, chuẩn hoá về `original.mp4`.
- Lấy metadata (tiêu đề, thời lượng, kích thước, nền tảng) ghi vào DB và `meta.json`.
- Tạo thumbnail bằng ffmpeg.
- Frontend React: nhập nhiều link, hàng đợi job, thư viện video, trang phát video, trang cài đặt.
- Các endpoint xem/xoá/mở thư mục/stream video.

## Backend

| File | Vai trò |
|---|---|
| `backend/app/main.py` | App factory, lifespan, DB init, worker start/stop, CORS, mount static + SPA fallback |
| `backend/app/config.py` | `AppConfig` đọc `.env`; `DATA_DIR`, timeout, bind host/port, đường dẫn DB/videos/assets |
| `backend/app/db.py` | Engine SQLite, session factory, `init_db()` |
| `backend/app/models.py` | SQLModel: `Video`, `Job`, `AppSettings` |
| `backend/app/schemas.py` | Pydantic request/response; validate URL đầu vào |
| `backend/app/worker.py` | Worker thread, `JobContext`, timeout hợp tác, handler `download` |
| `backend/app/routers/videos.py` | Download, list/detail, stream, thumbnail, xoá, mở thư mục |
| `backend/app/routers/jobs.py` | Danh sách job + chi tiết job |
| `backend/app/routers/settings.py` | Đọc/ghi settings |
| `backend/app/routers/system.py` | `/api/health` (Phase 1); update yt-dlp thêm ở Phase 2 |
| `backend/app/services/urls.py` | Validate `http/https`, nhận diện nền tảng |
| `backend/app/services/downloader.py` | Wrapper yt-dlp, progress hook, metadata, `DownloadResult` |
| `backend/app/services/ffmpeg_utils.py` | `probe_video`, `ensure_mp4`, `make_thumbnail` bằng subprocess list args |
| `backend/app/settings_store.py` | Lấy/tạo dòng settings mặc định |
| `backend/app/ids.py` | Sinh id ngắn cho video/job |

### Luồng tải video

1. `POST /api/download` validate URL, tạo `Video` (status `downloading`) + `Job` (status `pending`).
2. Worker poll bảng `jobs`, claim job pending, chuyển sang `running`.
3. Handler đọc `cookies_browser` từ settings (rỗng thì không dùng cookies).
4. yt-dlp tải với `format=bv*+ba/b`, merge MP4, `noplaylist`, `continuedl`, `socket_timeout=30`.
5. Progress hook cập nhật `progress` (0–99%), message kèm tốc độ và ETA.
6. File không phải `.mp4` được remux bằng ffmpeg (`-c copy`), sau đó probe metadata.
7. Tạo thumbnail tại `min(1s, duration/2)`, rộng 640px.
8. Ghi `meta.json`, cập nhật `Video` sang `ready`; lỗi → `Job` và `Video` sang `failed` kèm error.

### API có ở Phase 1

| Method | Endpoint | Ghi chú |
|---|---|---|
| POST | `/api/download` | `{urls: string[], force?: bool}` → `{jobs, duplicates}` |
| GET | `/api/videos` | Mới nhất trước |
| GET | `/api/videos/{id}` | Chi tiết |
| DELETE | `/api/videos/{id}` | Xoá record + thư mục + job liên quan |
| GET | `/api/videos/{id}/file?variant=original\|output` | Stream, hỗ trợ HTTP Range |
| GET | `/api/videos/{id}/thumb` | JPEG |
| POST | `/api/videos/{id}/open-folder` | Mở Finder/Explorer/xdg-open |
| GET | `/api/jobs` | Lọc `?status=pending\|running\|done\|failed` |
| GET | `/api/jobs/{id}` | Trạng thái + tiến độ |
| GET/PUT | `/api/settings` | Đọc/ghi settings |
| GET | `/api/health` | Trạng thái ffmpeg/ffprobe/yt-dlp (bổ sung ngoài plan) |

### Data model

- **Video:** id, source_url, platform, title, duration_sec, width, height, dir_path, file_path,
  thumb_path, status (`downloading|ready|failed`), error, has_subtitle, has_voice, has_output,
  created_at.
- **Job:** id, video_id (nullable), type (`download`...), status (`pending|running|done|failed`),
  progress, message, error, params (JSON), created_at, finished_at.
- **AppSettings:** logo, TTS, phụ đề, `whisper_model`, `cookies_browser` (một dòng duy nhất).

## Frontend

| File | Vai trò |
|---|---|
| `frontend/src/pages/Home.tsx` | Textarea nhiều link, nút tải, cảnh báo trùng, hàng đợi job, lưới thư viện |
| `frontend/src/pages/VideoDetail.tsx` | Player Original/Final, metadata, trạng thái các bước, mở thư mục, xoá |
| `frontend/src/pages/Settings.tsx` | Cookies trình duyệt + thông số cho phase sau (lưu SQLite) |
| `frontend/src/components/Header.tsx` | Điều hướng + badge cảnh báo thiếu công cụ |
| `frontend/src/components/JobCard.tsx` | Progress bar, message, lỗi job |
| `frontend/src/components/VideoCard.tsx` | Thumbnail, tiêu đề, thời lượng, badge nền tảng/trạng thái |
| `frontend/src/api.ts` | Typed client cho toàn bộ API |
| `frontend/src/index.css` | Tailwind 4 + design tokens dark |

Hành vi UI:

- Poll `/api/jobs` mỗi 1,5s; khi có job kết thúc thì refresh thư viện.
- Video đang tải hiện skeleton/placeholder; video lỗi hiện error.
- Phát video qua `/api/videos/{id}/file?variant=original`, seek được nhờ Range.
- Nút "Vẫn tải lại" gọi `force=true`, tạo video mới.

## Bảo mật / an toàn

- Chỉ nhận URL `http/https`, có host.
- Path video/thumbnail/stream luôn kiểm tra nằm trong `DATA_DIR/videos/{id}`.
- Xoá video kiểm tra thư mục nằm trong `DATA_DIR/videos` trước khi `rmtree`.
- ffmpeg/ffprobe chạy bằng `subprocess.run` với list args, không `shell=True`.
- Không hard-code secret; `.env` bị gitignore.
- CORS chỉ cho Vite dev; server bind `127.0.0.1` mặc định.

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `pytest` | **70 passed** |
| `ruff check backend` | All checks passed |
| `npm run build` | `tsc --noEmit` + Vite build OK |
| Smoke test | uvicorn `:8123`, `DATA_DIR=/tmp` |

Smoke test Phase 1 đã xác nhận:

- Tải `https://www.w3schools.com/html/mov_bbb.mp4` → job `done` 100%, video `ready` 320×176.
- `meta.json`, `thumb.jpg`, `original.mp4` được tạo; thumbnail trả `200 image/jpeg`.
- Range `bytes=0-9` → `206`.
- Dán trùng link → cảnh báo duplicate; `force` tạo video mới.
- URL sai scheme → `422`; URL lỗi → job `failed` kèm lỗi yt-dlp, app không crash.
- `DELETE` → `204`, xoá record + thư mục + job.

## Hạn chế tại thời điểm Phase 1

- Chưa xử lý riêng Douyin (link rút gọn/redirect).
- Chưa có retry khi yt-dlp lỗi.
- Chưa có fallback HTTP.
- Chưa có nút cập nhật yt-dlp.

Các mục này được giải quyết ở Phase 2 — xem [phase-2.md](phase-2.md).
