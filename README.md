# Reup Studio

Web app chạy **local** để tải video (Facebook Reel, Douyin, TikTok, YouTube Shorts...) về máy và
chuẩn bị cho quy trình thêm phụ đề, giọng đọc, logo rồi render. Không đăng nhập, không cloud,
không multi-user.

> **Trạng thái: Phase 1/6** — tải video + thư viện + phát video. Phụ đề/TTS/render sẽ được thêm
> ở các phase tiếp theo (xem cuối README).

## Yêu cầu

- Python **3.11+**
- Node.js **20+** và npm
- `ffmpeg` + `ffprobe` trong `PATH` (`brew install ffmpeg` trên macOS)
- `yt-dlp` được cài như **Python library** qua `pip` (không cần binary riêng)

App kiểm tra công cụ lúc khởi động, hiển thị badge **“Thiếu công cụ”** trên header và trả danh sách
trong `GET /api/health` nếu thiếu. App vẫn khởi động để bạn thấy lỗi trong UI; tải video sẽ fail
với thông báo rõ ràng.

## Cài & chạy

```bash
cp .env.example .env   # tuỳ chọn, mọi giá trị đều có mặc định

make setup             # tạo .venv, cài backend + frontend deps
make dev               # backend :8000 (reload) + Vite :5173
```

Mở http://127.0.0.1:5173.

Bản production-style (FastAPI serve luôn frontend đã build):

```bash
make run               # build frontend, mở http://127.0.0.1:8000
```

### Lệnh khác

```bash
make test              # pytest (backend)
make lint              # ruff
make build             # build frontend
```

## Cách dùng (Phase 1)

1. Dán một hoặc nhiều link vào ô **Danh sách link**, mỗi dòng một link. Chỉ nhận `http/https`.
2. Bấm **Tải video**. Mỗi link tạo một job `download` chạy trong worker thread.
3. Job đang chạy hiện progress bar (polling `/api/jobs` mỗi 1,5s). Link lỗi hiện job `failed` kèm
   lỗi gốc của yt-dlp.
4. Video tải xong xuất hiện trong **Thư viện** với thumbnail, tiêu đề, thời lượng, nền tảng.
   Click để phát video (hỗ trợ tua — HTTP Range), mở thư mục hoặc xoá.
5. Dán lại một link đã có: app cảnh báo trùng. **Vẫn tải lại** sẽ tạo một thư mục/video mới, không
   bao giờ ghi đè `original.mp4` cũ.

Dữ liệu nằm trong `data/` (đã gitignore):

```
data/
  app.db
  videos/{id}/
    original.mp4
    thumb.jpg
    meta.json
```

## Cấu hình

`.env` (xem `.env.example`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATA_DIR` | `./data` | Nơi lưu DB, video, asset |
| `ANTHROPIC_API_KEY` | rỗng | Dùng cho dịch phụ đề (Phase 4) |
| `DOUYIN_FALLBACK_URL` | rỗng | Fallback downloader Douyin (Phase 2) |
| `JOB_TIMEOUT_SEC` | `900` | Giới hạn thời gian 1 job |

Settings trong UI (lưu ở bảng `settings`): cookies trình duyệt, model Whisper, ngôn ngữ đích,
vị trí/cỡ phụ đề, giọng TTS, tốc độ, cấu hình logo.

### Cookies

Chọn trình duyệt ở **Cài đặt → Cookies trình duyệt** để yt-dlp đọc cookies
(`cookiesfrombrowser`). Cần cho Douyin hoặc video Facebook yêu cầu đăng nhập. Đóng trình duyệt
nếu yt-dlp báo không đọc được cookie (một số bản Chrome khoá file cookie khi đang chạy).

## API chính

| Method | Endpoint | Ghi chú |
|---|---|---|
| POST | `/api/download` | `{urls: string[], force?: bool}` → `{jobs, duplicates}` |
| GET | `/api/videos` | Mới nhất trước |
| GET | `/api/videos/{id}` | Chi tiết |
| DELETE | `/api/videos/{id}` | Xoá record + thư mục + job liên quan |
| GET | `/api/videos/{id}/file?variant=original\|output` | Stream, hỗ trợ Range |
| GET | `/api/videos/{id}/thumb` | JPEG |
| POST | `/api/videos/{id}/open-folder` | Mở Finder/Explorer |
| GET | `/api/jobs` | `?status=pending\|running\|done\|failed` |
| GET | `/api/jobs/{id}` | Trạng thái + tiến độ |
| GET/PUT | `/api/settings` | Đọc/ghi settings |
| GET | `/api/health` | Trạng thái ffmpeg/ffprobe/yt-dlp |

## Quyết định triển khai (ghi chú)

- **Repo root là project root** (không có thư mục con `video-tool/` như cây thư mục minh hoạ trong
  PLAN).
- Dùng **SQLModel** (được PLAN cho phép) để giảm boilerplate.
- **Không kill app khi thiếu tool**: log lỗi + `/api/health` + badge UI; tránh việc server chết
  trước khi người dùng kịp đọc lỗi.
- **Timeout job** được enforce hợp tác qua progress hook (`ctx.check_deadline`) và
  `socket_timeout=30` của yt-dlp. Download chạy in-process nên không thể kill cứng như subprocess.
- **Thumbnail lỗi không làm fail job**: video vẫn `ready`, chỉ thiếu ảnh bìa.
- **Re-download luôn tạo id/thư mục mới** (`force=true`), bảo đảm không ghi đè `original.mp4`.
- Path video luôn dựng từ `DATA_DIR + id`; endpoint file/thumbnail kiểm tra path nằm trong thư mục
  video. Mọi lệnh ffmpeg/yt-dlp dùng list args, không `shell=True`.

## Troubleshooting

| Triệu chứng | Cách xử lý |
|---|---|
| `ffmpeg not found` / badge “Thiếu công cụ” | Cài ffmpeg và mở lại app |
| Facebook/Douyin báo lỗi login / 403 | Chọn cookies trình duyệt trong Settings |
| yt-dlp lỗi “Unsupported URL” / extractor hỏng | `make setup` lại hoặc `.venv/bin/pip install -U yt-dlp`; nút update trong UI ở Phase 2 |
| Douyin vẫn lỗi | Cần cookies; fallback `DOUYIN_FALLBACK_URL` sẽ có ở Phase 2 |
| Whisper chậm | Chọn model `base`/`tiny` (Phase 4) |

Video Douyin có watermark chạy ngang — ngoài scope, không xử lý.

## Roadmap theo PLAN

- **Phase 2**: Douyin chuẩn hoá link, cookies, fallback HTTP, nút update yt-dlp, retry.
- **Phase 3**: upload logo + overlay ffmpeg.
- **Phase 4**: Whisper transcribe, dịch bằng Claude, sửa phụ đề, burn.
- **Phase 5**: edge-tts khớp timing, mix audio (mute/duck/keep).
- **Phase 6**: render gộp 1 lệnh ffmpeg, progress thật, preset, dọn file tạm.

Chỉ dùng cho mục đích cá nhân; bạn tự chịu trách nhiệm khi đăng lại nội dung.
