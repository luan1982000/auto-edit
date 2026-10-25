# Phase 2 — Douyin + độ bền của download

- **Commit:** `7467b7d` (base `d5e8b5b`)
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng
- **Tài liệu phase trước:** [phase-1.md](phase-1.md)

## Phạm vi đã làm

- Hỗ trợ `cookies_browser` trong settings → truyền `cookiesfrombrowser` cho yt-dlp.
- Chuẩn hoá mọi dạng link Douyin trước khi tải.
- Retry tối đa 2 lần (tổng 3 lần thử) với backoff 1s → 2s.
- Thông báo lỗi Douyin giữ lỗi gốc + gợi ý cookies / update / fallback.
- Fallback HTTP tuỳ chọn qua `DOUYIN_FALLBACK_URL` (mặc định tắt).
- Endpoint + nút **Cập nhật yt-dlp** trong Cài đặt.
- Chuyển cấu hình AI sang **DeepSeek** cho Phase 4.

## File mới / thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/services/douyin.py` | **Mới** — resolve link rút gọn, chuẩn hoá link, sinh gợi ý lỗi |
| `backend/app/services/fallback.py` | **Mới** — tải MP4 qua HTTP fallback an toàn |
| `backend/app/services/updater.py` | **Mới** — chạy `pip install --upgrade yt-dlp` |
| `backend/app/services/downloader.py` | Tách `_download_once`, thêm `retry_call`, retry + progress message |
| `backend/app/worker.py` | Chuẩn hoá Douyin, fallback, cập nhật `source_url`, `meta.json` |
| `backend/app/routers/system.py` | Thêm `POST /api/system/update-ytdlp` |
| `backend/app/config.py` | Thêm DeepSeek config, bỏ `anthropic_api_key` |
| `.env.example` | Thêm `DEEPSEEK_*`, giữ `DOUYIN_FALLBACK_URL` |
| `frontend/src/api.ts` | Thêm type + gọi API update yt-dlp |
| `frontend/src/pages/Settings.tsx` | Hiện version yt-dlp, nút cập nhật, output/restart note |
| `README.md` | Hướng dẫn Douyin, retry, fallback, update, DeepSeek |

## Chuẩn hoá link Douyin

Các dạng được nhận:

| Input | Output |
|---|---|
| `https://www.douyin.com/video/{id}` | Giữ nguyên URL chuẩn |
| `https://www.douyin.com/share/video/{id}?...` | `https://www.douyin.com/video/{id}` |
| `https://www.iesdouyin.com/share/video/{id}` | `https://www.douyin.com/video/{id}` |
| `https://www.douyin.com/?modal_id={id}` | `https://www.douyin.com/video/{id}` |
| `?vid=` / `?video_id={id}` | `https://www.douyin.com/video/{id}` |
| `https://v.douyin.com/{code}/` | Resolve redirect → URL chuẩn nếu host vẫn là Douyin |

Quy tắc an toàn:

- Chỉ nhận URL `http/https`.
- Link rút gọn được resolve bằng HEAD, fallback sang GET có Range, timeout 10s.
- Redirect chỉ được chấp nhận nếu host đích vẫn thuộc `douyin.com` / `iesdouyin.com`.
- Resolve lỗi hoặc redirect ra ngoài → dùng URL gốc để yt-dlp vẫn thử được.
- URL chuẩn được lưu vào `Video.source_url` và `meta.json.url` để cảnh báo trùng chính xác hơn.

## Retry

- `retry_call()` chỉ retry `DownloadError` của yt-dlp.
- Số lần: `retries=2` → tối đa **3 lần thử** (1 đầu + 2 retry).
- Backoff: `1s`, rồi `2s`.
- Job timeout (`JobTimeoutError`) không bị retry; deadline được kiểm tra trước mỗi lần retry.
- Progress message khi retry: `Lỗi: <dòng đầu> — thử lại 1/2...`
- yt-dlp nội bộ vẫn có `retries=2` cho network/fragment; retry của app là retry toàn bộ lần tải.

## Gợi ý lỗi Douyin

`with_douyin_hint()` giữ nguyên message gốc của yt-dlp rồi thêm các dòng `Gợi ý:`:

- Lỗi login/cookie/private/403 → gợi ý chọn cookies trình duyệt + cập nhật yt-dlp.
- Lỗi unsupported/extractor/no formats → gợi ý cập nhật yt-dlp + cookies.
- Nếu fallback chưa bật → thêm gợi ý bật `DOUYIN_FALLBACK_URL`.
- Hàm idempotent: message đã có `Gợi ý:` thì không thêm lần nữa.

## Fallback HTTP (tuỳ chọn)

Bật bằng `.env`:

```bash
DOUYIN_FALLBACK_URL=http://127.0.0.1:9000/download
```

Hợp đồng:

- App gọi `GET {DOUYIN_FALLBACK_URL}?url=<link Douyin đã chuẩn hoá>`.
- Query có sẵn của base URL được giữ, tham số `url` cũ bị thay.
- Service trả `200` với **body là file MP4**.
- Chỉ chạy cho Douyin và chỉ khi yt-dlp thất bại.
- Không ghi đè `original.mp4` đã tồn tại.
- Ghi ra `<target>.part` rồi `os.replace` atomically; xoá `.part` trong `finally`.
- Kiểm tra scheme của redirect cuối vẫn là `http/https`.
- Có timeout tổng (mặc định 300s) + deadline của job; body rỗng bị coi là lỗi.
- Lỗi fallback được gộp vào message cuối: `yt-dlp lỗi ...\n\nFallback cũng thất bại: ...`.

## Cập nhật yt-dlp

- Endpoint: `POST /api/system/update-ytdlp`.
- Lệnh cố định: `[sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]` — list args, không shell, không nhận input từ client.
- Timeout 180s; stdout + stderr được gộp và cắt còn 4000 ký tự cuối.
- Trả `{ok, output, version, restart_required}`; lỗi pip trả `200` với `ok=false` để UI hiển thị output.
- Version đọc bằng `importlib.metadata.version("yt-dlp")`.
- **Cần restart backend** vì tiến trình đang chạy đã import module yt-dlp cũ.

UI Cài đặt:

- Hiển thị version hiện tại lấy từ `/api/health`.
- Nút **Cập nhật yt-dlp**, spinner khi chạy.
- Panel output thành công/thất bại + nhắc restart.

## DeepSeek cho Phase 4

Theo yêu cầu, thay Claude API bằng DeepSeek (OpenAI-compatible):

| Biến | Mặc định |
|---|---|
| `DEEPSEEK_API_KEY` | rỗng |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | `deepseek-chat` |

Phase 2 chỉ thêm config; **chưa có code transcribe/dịch**.

## Luồng worker sau Phase 2

1. Xác định `platform` từ Video hoặc `detect_platform(url)`.
2. Nếu là Douyin → `normalize_douyin_url(url)`; lưu URL chuẩn vào `Video.source_url`.
3. Gọi `download_video(...)` (có retry).
4. Nếu là Douyin và yt-dlp lỗi:
   - Chưa cấu hình fallback → raise `DownloadError` kèm gợi ý.
   - Có fallback → gọi `download_via_fallback`; thành công tạo `DownloadResult` với
     `title="Douyin video"`, `platform="douyin"`; thất bại → error gộp cả hai.
5. Probe, tạo thumbnail, ghi `meta.json` gồm:
   - `url` (URL đã chuẩn hoá)
   - `source_input` (link người dùng dán)
   - `fallback` (bool)
6. Cập nhật Video sang `ready` (hoặc `failed` nếu lỗi).

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `pytest` | **110 passed**, 1 warning deprecation Starlette/httpx |
| `ruff check backend` | All checks passed |
| `npm run build` | OK (CSS 42.26 kB, JS 295.86 kB) |
| Smoke test | uvicorn `127.0.0.1:8124`, `DATA_DIR=/tmp/bot-reup-phase2-smoke` |

Phân bổ test hiện tại:

| File | Số test |
|---|---|
| `test_api.py` | 21 |
| `test_douyin.py` | 17 |
| `test_downloader.py` | 10 |
| `test_fallback.py` | 7 |
| `test_ffmpeg_utils.py` | 6 |
| `test_retry.py` | 5 |
| `test_updater.py` | 5 |
| `test_urls.py` | 26 |
| `test_worker.py` | 13 |

Smoke test Phase 2 đã xác nhận:

- `/api/health`: ffmpeg/ffprobe/yt_dlp đều `true`, yt-dlp `2026.10.21`, không có problem.
- Tải MP4 thường (w3schools) → job `done` 100%, video `ready` 320×176.
- Link Douyin giả (`iesdouyin.com/share/video/...`) → job `failed` với lỗi cookies gốc của yt-dlp,
  kèm gợi ý cookies + fallback; `source_url` được chuẩn hoá thành
  `https://www.douyin.com/video/...`.
- `POST /api/system/update-ytdlp` → `200`, `ok=true`, version `2026.10.21`,
  `restart_required=true`, output pip thật.

**Chưa kiểm chứng:**

- Tải một link Douyin công khai thật end-to-end (không có link trong phiên test).
- Fallback với service thật (mới test bằng HTTP server cục bộ trong unit test).
- Nhánh thành công của fallback trên video Douyin thật.

Dữ liệu thật trong `data/` (Facebook Reel và link rednote failed) được giữ nguyên, không xoá/sửa.

## Quyết định đã chốt

- "Retry tối đa 2 lần" = 2 retry sau lần đầu (3 lần thử), khớp README.
- Retry mọi `DownloadError` thay vì phân loại lỗi tạm thời/phía server; đơn giản và an toàn hơn,
  đổi lại vài giây chờ với lỗi vĩnh viễn. Timeout không retry.
- Fallback chỉ nhận cấu hình từ `.env`, không nhận URL service từ client; chỉ Douyin.
- Chỉ `POST` là contract của endpoint update yt-dlp; `GET` có thể trả 404 (SPA fallback) hoặc 405.
- DeepSeek thay Claude cho Phase 4; key thiếu chỉ tắt tính năng dịch, không ảnh hưởng tính năng khác.
