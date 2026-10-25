# Reup Studio

Web app chạy **local** để tải video (Facebook Reel, Douyin, TikTok, YouTube Shorts...) về máy và
chuẩn bị cho quy trình thêm phụ đề, giọng đọc, logo rồi render. Không đăng nhập, không cloud,
không multi-user.

> **Trạng thái: Phase 2/6** — tải video (kể cả Douyin), thư viện, phát video, cập nhật yt-dlp.
> Phụ đề/TTS/render sẽ được thêm ở các phase tiếp theo (xem cuối README).

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

## Cách dùng (Phase 2)

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
| `DEEPSEEK_API_KEY` | rỗng | Dịch phụ đề bằng DeepSeek (Phase 4) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Base URL API DeepSeek (OpenAI-compatible) |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model dùng để dịch (Phase 4) |
| `DOUYIN_FALLBACK_URL` | rỗng | HTTP fallback cho Douyin, tắt khi rỗng (xem bên dưới) |
| `JOB_TIMEOUT_SEC` | `900` | Giới hạn thời gian 1 job |

Settings trong UI (lưu ở bảng `settings`): cookies trình duyệt, model Whisper, ngôn ngữ đích,
vị trí/cỡ phụ đề, giọng TTS, tốc độ, cấu hình logo.

### Cookies

Chọn trình duyệt ở **Cài đặt → Cookies trình duyệt** để yt-dlp đọc cookies
(`cookiesfrombrowser`). Cần cho Douyin hoặc video Facebook yêu cầu đăng nhập. Đóng trình duyệt
nếu yt-dlp báo không đọc được cookie (một số bản Chrome khoá file cookie khi đang chạy).

### Douyin & độ bền của download

- App chuẩn hoá các dạng link Douyin trước khi tải:
  `https://v.douyin.com/{code}/` (theo redirect), `https://www.douyin.com/video/{id}`,
  `/share/video/{id}`, `https://www.iesdouyin.com/share/video/{id}` và
  `?modal_id={id}` → `https://www.douyin.com/video/{id}`. URL chuẩn được lưu vào
  `source_url`/`meta.json` để lần sau cảnh báo trùng chính xác hơn.
- yt-dlp được thử tối đa **3 lần** (1 lần đầu + 2 retry), backoff nhẹ 1s rồi 2s. Lỗi timeout
  của job không bị retry.
- Nếu tải Douyin thất bại, thông báo lỗi giữ nguyên lỗi gốc của yt-dlp kèm gợi ý: chọn cookies
  trình duyệt, cập nhật yt-dlp, hoặc bật fallback.
- Nút **Cập nhật yt-dlp** ở Cài đặt chạy `python -m pip install --upgrade yt-dlp` và hiển thị
  output. yt-dlp đã import trong tiến trình cũ, nên **khởi động lại backend** sau khi cập nhật.

#### Fallback HTTP (tuỳ chọn, mặc định tắt)

Đặt `DOUYIN_FALLBACK_URL` trong `.env` nếu bạn có một service tải Douyin riêng. Hợp đồng:

- App gọi `GET {DOUYIN_FALLBACK_URL}?url=<link Douyin đã chuẩn hoá>` (query có sẵn được giữ,
  tham số `url` cũ bị thay).
- Service trả `200` với **nội dung file MP4** (không phải JSON/HTML). App lưu vào `original.mp4`
  và không ghi đè file đã tồn tại.
- Chỉ dùng cho Douyin và chỉ khi yt-dlp lỗi. Chỉ trỏ tới service bạn tin cậy.

```bash
# .env
DOUYIN_FALLBACK_URL=http://127.0.0.1:9000/download
```

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
| POST | `/api/system/update-ytdlp` | `pip install --upgrade yt-dlp`, trả output + version |

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
- **Chuẩn hoá Douyin**: chỉ chấp nhận redirect về host `douyin.com`/`iesdouyin.com`; nếu resolve
  lỗi hoặc redirect ra ngoài, app dùng URL gốc để yt-dlp vẫn thử được.
- **Retry** áp dụng cho mọi `DownloadError` của yt-dlp (kể cả login/unsupported) để đơn giản;
  job timeout không bị retry.
- **Fallback Douyin** chỉ chạy khi được cấu hình, trả file MP4 và không ghi đè `original.mp4`.
- **Update yt-dlp** chạy bằng `sys.executable -m pip ...` với list args cố định, không nhận input
  từ client; cần restart backend để nạp module mới.
- **Dịch phụ đề (Phase 4) dùng DeepSeek API** (`DEEPSEEK_API_KEY`) thay cho Claude, theo yêu cầu;
  key đọc từ `.env`, thiếu key chỉ tắt tính năng dịch.
- Path video luôn dựng từ `DATA_DIR + id`; endpoint file/thumbnail kiểm tra path nằm trong thư mục
  video. Mọi lệnh ffmpeg/yt-dlp dùng list args, không `shell=True`.

## Troubleshooting

| Triệu chứng | Cách xử lý |
|---|---|
| `ffmpeg not found` / badge “Thiếu công cụ” | Cài ffmpeg và mở lại app |
| Facebook/Douyin báo lỗi login / 403 | Chọn cookies trình duyệt trong Settings |
| yt-dlp lỗi “Unsupported URL” / extractor hỏng | Bấm **Cập nhật yt-dlp** trong Cài đặt (hoặc `.venv/bin/pip install -U yt-dlp`), rồi khởi động lại backend |
| Douyin vẫn lỗi | Chọn cookies trình duyệt, cập nhật yt-dlp; nếu vẫn lỗi, bật `DOUYIN_FALLBACK_URL` |
| Whisper chậm | Chọn model `base`/`tiny` (Phase 4) |

Video Douyin có watermark chạy ngang — ngoài scope, không xử lý.

## Roadmap theo PLAN

- **Phase 2 (xong)**: Douyin chuẩn hoá link, cookies, fallback HTTP, nút update yt-dlp, retry.
- **Phase 3**: upload logo + overlay ffmpeg.
- **Phase 4**: Whisper transcribe, dịch bằng **DeepSeek API**, sửa phụ đề, burn.
- **Phase 5**: edge-tts khớp timing, mix audio (mute/duck/keep).
- **Phase 6**: render gộp 1 lệnh ffmpeg, progress thật, preset, dọn file tạm.

Chỉ dùng cho mục đích cá nhân; bạn tự chịu trách nhiệm khi đăng lại nội dung.
