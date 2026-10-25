# Đã triển khai — Reup Studio

Ghi nhận những gì đã làm xong, đối chiếu với [`plan.md`](../plan.md).
Cập nhật lần cuối: **2026-10-25**.

## Trạng thái các phase

| Phase | Nội dung | Trạng thái | Tài liệu |
|---|---|---|---|
| 1 | Skeleton + Download + List | ✅ Xong | [phase-1.md](phase-1.md) |
| 2 | Douyin + độ bền của download | ✅ Xong | [phase-2.md](phase-2.md) |
| 3 | Logo overlay | ✅ Xong | [phase-3.md](phase-3.md) |
| 4 | Phụ đề (Whisper + dịch + burn) | ✅ Xong | [phase-4.md](phase-4.md) |
| 5 | TTS + mix audio | ✅ Xong | [phase-5.md](phase-5.md) |
| 6 | Render gộp + hoàn thiện | ✅ Xong | [phase-6.md](phase-6.md) |
| 7 | Che phụ đề cũ + chọn ngôn ngữ (bổ sung) | ✅ Xong | [phase-7.md](phase-7.md) |
| 8 | Upload video từ máy (bổ sung) | ✅ Xong | [phase-8.md](phase-8.md) |

> Dịch phụ đề dùng **DeepSeek API** thay cho Claude API trong plan, theo yêu cầu. Config nằm trong
> `.env`; thiếu key chỉ tắt tính năng dịch.

## App hiện làm được gì

- Dán nhiều link (mỗi dòng một link) → tạo job tải; chỉ nhận `http/https`.
- Tải video qua yt-dlp: Facebook Reel, Douyin, TikTok, YouTube Shorts...
- Upload video có sẵn từ máy (tối đa 2 GB), kéo thả hoặc chọn file; chuẩn hoá về
  `original.mp4`, tạo thumbnail và thêm thẳng vào thư viện.
- Chuẩn hoá link Douyin rút gọn/chia sẻ, retry 2 lần, fallback HTTP tuỳ chọn.
- Thư viện video: thumbnail, tiêu đề, thời lượng, nền tảng, trạng thái.
- Phát video trong browser, tua được nhờ HTTP Range; mở thư mục; xoá video.
- Cảnh báo link trùng; tải lại luôn tạo thư mục mới, không ghi đè bản cũ.
- Upload logo PNG/JPEG/WEBP, xem trước vị trí, chỉnh góc/kích thước/độ mờ/margin.
- Nhận dạng phụ đề bằng faster-whisper (model chọn được), dịch bằng DeepSeek, sửa/thêm/xoá dòng.
- Tạo lại phụ đề từ đầu cho video đã có phụ đề (có xác nhận trước khi ghi đè).
- Chọn ngôn ngữ nói (24 mã hoặc tự động) và ngôn ngữ đích (25 mã, gồm Trung Phồn thể) mỗi lần
  tạo/dịch phụ đề.
- Chụp 3 ảnh mẫu trong video, kéo chuột khoanh vùng phụ đề cũ; render phủ vùng đó bằng `drawbox`
  trước logo/ASS mới nên phụ đề cũ bị ghi đè.
- Burn phụ đề ASS theo font/cỡ/vị trí, tự xuống dòng cho video dọc/ngang.
- Tạo giọng đọc edge-tts (2 giọng Việt, tốc độ -20%…+20%), nghe thử, ghép timing theo segment.
- Render gộp logo + phụ đề + voice trong một lệnh ffmpeg, 3 chế độ âm thanh gốc, progress thật.
- Preset render trong Settings; tab Original/Output; tải output; mở thư mục.
- Cập nhật yt-dlp bằng một nút trong Cài đặt (cần restart backend).

## Chạy

```bash
make setup     # tạo .venv + cài backend/frontend deps
make dev       # backend :8000 (reload) + Vite :5173
# hoặc bản production-style:
make run       # build frontend, serve tại http://127.0.0.1:8000

make test      # pytest
make lint      # ruff
make build     # build frontend
```

## Dữ liệu

```
data/
  app.db
  assets/
    logo.png
  videos/{id}/
    original.mp4
    thumb.jpg
    meta.json
    frames/sample-*.jpg
    cover_region.json
    subtitle.json
    subtitle.srt
    subtitle.ass
    voice.mp3
    output_final.mp4
```

- `original.mp4` **không bao giờ bị ghi đè**; tải lại luôn tạo id/thư mục mới.
- `output_final.mp4` ghi qua file tạm rồi `replace`; render lỗi giữ nguyên output cũ.
- `audio.wav` là file tạm, được xoá sau transcribe (trừ khi bước trích audio lỗi giữa chừng).
- `cover_region.json` lưu toạ độ chuẩn hoá `0..1`; file hỏng làm render fail rõ ràng.
- Video path luôn dựng từ `DATA_DIR + id`, không nhận path từ client.

## Lịch sử commit

| Commit | Nội dung |
|---|---|
| `c4e28cf` | init project with plan |
| `d5e8b5b` | Phase 1 — local video downloader, library and streaming UI |
| `7467b7d` | Phase 2 — Douyin normalization, retries, fallback and yt-dlp update |
| `198e199` | Phase 3 — logo upload, preview and ffmpeg overlay render |
| `d32f8d1` | Phase 4 — subtitle transcription, DeepSeek translation and ASS burn-in |
| `41955d1` | Phase 5 — Edge TTS voice-over, timeline mixing and ducked render |
| `c0805cf` | Phase 6 — render presets, settings migration and combo coverage |
| `58be7e5` | Phase 7–8 — che phụ đề cũ, chọn ngôn ngữ, upload video từ máy |

Tài liệu trong thư mục `implemented/` được cập nhật cùng Phase 7–8.

## Kiểm chứng mới nhất

- `pytest -o addopts="" -q`: **350 passed** trong 14.35s.
- `ruff check app tests`: All checks passed.
- `npm run build`: TypeScript + Vite build OK (CSS 48.19 kB, JS 338.51 kB; gzip 8.91/101.32 kB).
- Smoke TTS thật từ Phase 5: 2 segment, `voice.mp3` dài 6.05s so với video 6.0s.
- Smoke render gộp thật từ Phase 5/6: logo + ASS + voice (duck) trong 1 lệnh ffmpeg →
  `output_final.mp4` 6.01s, 640×360, có audio; progress `-progress pipe:1` chạy tới 100%.
- Test ảnh mẫu dùng ffmpeg thật; filter `drawbox` và đường đi vùng che có unit test.

Phân bổ test hiện tại:

| File | Số test |
|---|---|
| `test_api.py` | 23 |
| `test_cover.py` | 14 |
| `test_db.py` | 1 |
| `test_douyin.py` | 17 |
| `test_downloader.py` | 11 |
| `test_fallback.py` | 7 |
| `test_ffmpeg_utils.py` | 14 |
| `test_frames.py` | 3 |
| `test_languages.py` | 12 |
| `test_logo_render_api.py` | 11 |
| `test_render.py` | 42 |
| `test_retry.py` | 5 |
| `test_subtitle_api.py` | 15 |
| `test_subtitle_region_api.py` | 9 |
| `test_subtitles.py` | 18 |
| `test_system.py` | 2 |
| `test_transcribe.py` | 8 |
| `test_translate.py` | 11 |
| `test_tts.py` | 27 |
| `test_tts_api.py` | 9 |
| `test_updater.py` | 5 |
| `test_upload.py` | 8 |
| `test_urls.py` | 26 |
| `test_worker.py` | 19 |
| `test_worker_render.py` | 13 |
| `test_worker_subtitles.py` | 14 |
| `test_worker_tts.py` | 6 |

**Chưa kiểm chứng end-to-end với dữ liệu thật:**

- Tải một link Douyin công khai thật (không có link trong phiên test).
- Gọi DeepSeek API thật (chưa có `DEEPSEEK_API_KEY` trong `.env`); toàn bộ parsing/lỗi được test
  bằng HTTP client giả.
- Chạy trọn quy trình UI bằng một link thật. Các mảnh đã được test riêng và smoke thật: edge-tts +
  render gộp; transcribe/render/ảnh mẫu được test với ffmpeg thật và engine giả.
- Thao tác kéo/thả vùng che trong trình duyệt thật (logic toạ độ và API đã có test).
- Kéo/thả hoặc chọn file upload trên trình duyệt thật; test upload dùng TestClient + ffmpeg thật,
  chưa thử file sát 2 GB hay codec lạ.

Dữ liệu thật trong `data/` được giữ nguyên, không xoá/sửa trong quá trình test.

## Ghi chú

- Mọi lệnh ffmpeg/yt-dlp dùng list args, không `shell=True`; voice/rate/tên file subtitle được
  validate bằng regex.
- Server bind `127.0.0.1`; CORS chỉ mở cho Vite dev (`localhost`/`127.0.0.1:5173`).
- Key DeepSeek đọc từ `.env`, không hard-code; thiếu key không ảnh hưởng tính năng khác.
