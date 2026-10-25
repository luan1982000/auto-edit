# PLAN: Local Video Downloader + Editor Web

## 1. Mục tiêu

Web app chạy **local** (không auth, không deploy), dùng cho 1 người:

1. Dán link video (Facebook Reel, Douyin, TikTok, YouTube Shorts...) → bấm **Download** → video lưu vào folder trên máy.
2. Trang danh sách các video đã tải (thumbnail, tiêu đề, thời lượng, nguồn, trạng thái).
3. Với mỗi video đã tải: tạo **phụ đề**, tạo **giọng đọc (TTS)**, tự động chèn **logo ở góc màn hình**, rồi render ra bản cuối.

Không cần: đăng nhập, multi-user, cloud, thanh toán.

## 2. Tech stack (đã chốt, đừng đổi nếu không có lý do)

| Thành phần | Chọn |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| DB | SQLite (qua SQLModel hoặc SQLAlchemy) |
| Download | `yt-dlp` (gọi bằng subprocess hoặc thư viện) |
| Xử lý video | `ffmpeg` / `ffprobe` (subprocess) |
| Speech-to-text | `faster-whisper` (local), model mặc định `small` |
| Dịch | Claude API (qua `anthropic` SDK), key đọc từ `.env` |
| TTS | `edge-tts` (mặc định, miễn phí), thiết kế interface để cắm thêm engine khác |
| Job queue | Không dùng Celery/Redis. Dùng worker thread + bảng `jobs` trong SQLite |
| Frontend | React + Vite + TypeScript + Tailwind. Build ra static, FastAPI serve luôn |
| Realtime tiến độ | Polling `/api/jobs/{id}` mỗi 1s (đơn giản), hoặc SSE nếu dễ |
| Chạy | `make dev` / `make run`; có `Dockerfile` + `docker-compose.yml` là tuỳ chọn |

Yêu cầu máy: đã cài `ffmpeg` trong PATH. App phải kiểm tra lúc khởi động và báo lỗi rõ ràng nếu thiếu `ffmpeg` hoặc `yt-dlp`.

## 3. Cấu trúc project

```
video-tool/
  PLAN.md
  README.md
  Makefile
  .env.example            # ANTHROPIC_API_KEY=, DATA_DIR=./data
  backend/
    pyproject.toml
    app/
      main.py             # FastAPI app, mount static, startup checks
      config.py           # đọc .env, đường dẫn DATA_DIR
      db.py               # engine, session, init tables
      models.py           # Video, Job, Settings
      schemas.py          # pydantic request/response
      routers/
        videos.py
        jobs.py
        settings.py
      services/
        downloader.py     # yt-dlp wrapper
        ffmpeg_utils.py   # probe, thumbnail, extract audio, render
        transcribe.py     # faster-whisper
        translate.py      # Claude API
        tts.py            # interface + EdgeTTSEngine
        render.py         # build lệnh ffmpeg gộp logo/sub/voice
      worker.py           # worker thread lấy job pending và chạy
    tests/
  frontend/
    package.json
    src/
      pages/              # Home (download + list), VideoDetail, Settings
      components/
      api.ts
  data/                   # gitignore
    app.db
    assets/logo.png
    videos/{id}/
      original.mp4
      thumb.jpg
      meta.json
      audio.wav           # tạm
      subtitle.srt
      voice.mp3
      output_final.mp4
```

Mỗi video 1 thư mục riêng. **Không bao giờ ghi đè `original.mp4`.**

## 4. Data model

**Video**
- `id` (uuid/short id), `source_url`, `platform`, `title`, `duration_sec`, `width`, `height`
- `dir_path`, `file_path`, `thumb_path`
- `status`: `downloading | ready | failed`
- `has_subtitle`, `has_voice`, `has_output` (bool, hoặc suy ra từ file tồn tại)
- `created_at`

**Job**
- `id`, `video_id` (nullable cho job download lúc chưa có video), `type`: `download | transcribe | translate | tts | render`
- `status`: `pending | running | done | failed`
- `progress` (0–100), `message`, `error`, `params` (JSON), `created_at`, `finished_at`

**Settings** (1 dòng, key-value cũng được)
- `logo_path`, `logo_position` (`tl|tr|bl|br`), `logo_scale_pct` (mặc định 15), `logo_opacity` (0–1), `logo_margin_px`
- `tts_engine` (`edge`), `tts_voice` (mặc định `vi-VN-HoaiMyNeural`), `tts_rate`
- `subtitle_font`, `subtitle_size`, `subtitle_position`, `target_language` (mặc định `vi`)
- `whisper_model` (mặc định `small`)
- `cookies_browser` (rỗng | `chrome` | `firefox`...) dùng cho yt-dlp

## 5. API

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/api/download` | body `{urls: string[]}`, tạo 1 job download cho mỗi link, trả về danh sách job |
| GET | `/api/videos` | danh sách video (mới nhất trước) |
| GET | `/api/videos/{id}` | chi tiết video + trạng thái các bước |
| DELETE | `/api/videos/{id}` | xoá DB record + xoá thư mục |
| GET | `/api/videos/{id}/file?variant=original\|output` | stream video (hỗ trợ Range để seek) |
| GET | `/api/videos/{id}/thumb` | thumbnail |
| POST | `/api/videos/{id}/transcribe` | chạy Whisper (+ dịch nếu `translate=true`) → tạo `subtitle.srt` |
| GET/PUT | `/api/videos/{id}/subtitle` | đọc/lưu phụ đề dạng JSON `[{start, end, text}]` |
| POST | `/api/videos/{id}/tts` | sinh `voice.mp3` từ phụ đề, khớp timing |
| POST | `/api/videos/{id}/render` | body `{logo: bool, subtitle: bool, voice: bool, keep_original_audio: "mute"\|"duck"\|"keep"}` |
| GET | `/api/jobs/{id}` | trạng thái + tiến độ |
| GET | `/api/jobs?status=` | list job (để UI hiện hàng đợi) |
| GET/PUT | `/api/settings` | đọc/ghi settings |
| POST | `/api/settings/logo` | upload logo (png, ưu tiên nền trong suốt) |
| POST | `/api/system/update-ytdlp` | chạy `pip install -U yt-dlp` |
| POST | `/api/videos/{id}/open-folder` | mở thư mục trong file explorer của OS |

Bind `127.0.0.1` mặc định. CORS chỉ cho origin của Vite dev.

## 6. Các phase triển khai

Làm lần lượt, **mỗi phase phải chạy được và có test/smoke test trước khi sang phase sau**. Commit sau mỗi phase.

### Phase 1: Skeleton + Download + List

**Việc cần làm**
- Khởi tạo backend FastAPI, SQLite, startup check `ffmpeg`/`yt-dlp`.
- Worker thread: poll job `pending`, chạy, cập nhật `progress`.
- `downloader.py`: dùng yt-dlp tải format tốt nhất, merge ra `original.mp4`, lấy metadata (title, duration) ghi vào DB + `meta.json`. Parse progress từ yt-dlp hook để cập nhật `progress`.
- Tạo thumbnail bằng ffmpeg (frame ở ~1s).
- Frontend: ô textarea nhập nhiều link (mỗi dòng 1 link), nút Download, lưới video (thumbnail, title, duration, platform badge, status), click vào để xem player, nút xoá, nút mở thư mục.
- Hiển thị job đang chạy với progress bar; job lỗi hiện thông báo lỗi.

**Done khi**
- Dán 1 link Facebook Reel và 1 link YouTube Shorts → tải về đúng folder, hiện trong danh sách, phát được trong browser.
- Link sai hoặc bị lỗi → job `failed` có message rõ, app không crash.
- Dán cùng 1 link 2 lần → cảnh báo trùng (dựa trên `source_url`), cho phép tải lại nếu user muốn.

### Phase 2: Douyin + độ bền của download

**Việc cần làm**
- Hỗ trợ `cookies_browser` trong settings → truyền `--cookies-from-browser`.
- Chuẩn hoá link Douyin (link rút gọn `v.douyin.com`, link `/video/{id}`).
- Nếu yt-dlp fail với Douyin: fallback sang một downloader HTTP tuỳ chọn (cấu hình `DOUYIN_FALLBACK_URL` trong `.env`, mặc định tắt). Ghi rõ trong README cách bật.
- Endpoint + nút "Update yt-dlp" trong Settings.
- Retry tối đa 2 lần với backoff nhẹ.

**Done khi**
- Có thể tải 1 link Douyin công khai (với cookies nếu cần). Nếu không tải được, thông báo lỗi nói rõ nguyên nhân gợi ý (cần cookies / cần update yt-dlp).

### Phase 3: Logo overlay

**Việc cần làm**
- Upload logo ở Settings, preview vị trí logo trên khung hình (CSS overlay mô phỏng là đủ).
- `render.py`: hàm build lệnh ffmpeg overlay logo, logo co theo `% chiều rộng video` bằng `scale2ref`, hỗ trợ opacity (`format=rgba,colorchannelmixer=aa=X`), margin, 4 góc.
- Nút Render trên trang chi tiết video, chỉ bật checkbox Logo ở bước này.
- Output: `output_final.mp4`, giữ audio gốc (`-c:a copy` nếu được), video `libx264 -crf 20 -preset medium`, `-movflags +faststart`.

**Gợi ý filter**
```
[1:v][0:v]scale2ref=w=iw*{pct}/100:h=ow/mdar[logo][base];
[logo]format=rgba,colorchannelmixer=aa={opacity}[logo2];
[base][logo2]overlay={x}:{y}
```
Với `x,y` theo góc, ví dụ góc phải-trên: `W-w-{margin}:{margin}`.

**Done khi**
- Render xong, logo xuất hiện đúng góc, đúng kích thước, trên cả video dọc 1080x1920 và video ngang.

### Phase 4: Phụ đề (transcribe + dịch + sửa + burn)

**Việc cần làm**
- `ffmpeg_utils`: tách audio 16kHz mono → `audio.wav`.
- `transcribe.py`: faster-whisper, trả segment `{start, end, text}` + ngôn ngữ phát hiện. Cho chọn model trong Settings. Cache model, progress theo segment.
- `translate.py`: gửi toàn bộ segment cho Claude trong **một request có cấu trúc** (JSON in/out), giữ nguyên số segment và timestamp, dịch sang `target_language`. Prompt yêu cầu câu ngắn gọn, tự nhiên, hợp phụ đề video ngắn. Nếu ngôn ngữ nguồn đã trùng target thì bỏ qua bước dịch.
- Lưu `subtitle.srt` + bản JSON.
- UI: bảng sửa phụ đề (start, end, text, sửa inline, thêm/xoá dòng), nút Save, nút "Dịch lại".
- Render: burn phụ đề bằng ffmpeg (`subtitles=` hoặc chuyển sang `.ass` để style: font, size, viền, vị trí dưới-giữa). Dùng font có hỗ trợ tiếng Việt, cho phép chọn file font trong settings.
- Tự xuống dòng khi dòng quá dài (giới hạn ~40 ký tự/dòng cho video dọc).

**Done khi**
- Video tiếng Trung → ra phụ đề tiếng Việt đúng timing, sửa được, burn lên video không lỗi dấu.

### Phase 5: Giọng đọc (TTS) + mix audio

**Việc cần làm**
- `tts.py`: interface `TTSEngine.synthesize(text, voice, rate) -> audio_file`. Triển khai `EdgeTTSEngine` (`edge-tts`).
- Sinh audio cho **từng segment**. Nếu audio dài hơn khung thời gian của segment: tăng tốc bằng `atempo` (tối đa 1.4x, vượt thì chấp nhận tràn nhẹ sang khoảng trống tiếp theo). Nếu ngắn hơn: đệm im lặng.
- Ghép tất cả thành `voice.mp3` đúng timeline (dùng `adelay` + `amix`, hoặc dựng bằng pydub rồi export).
- UI: chọn giọng (vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural), tốc độ, nút **nghe thử** 1 câu, nút Generate.
- Render: 3 chế độ audio gốc: `mute` / `duck` (giảm còn ~20%, dùng `sidechaincompress` hoặc `volume`) / `keep`; mix với `voice.mp3`.

**Done khi**
- Video có giọng đọc tiếng Việt khớp tương đối với phụ đề, audio gốc được ducking, không bị vỡ tiếng.

### Phase 6: Render gộp + hoàn thiện

**Việc cần làm**
- Gộp logo + phụ đề + voice vào **1 lệnh ffmpeg duy nhất** (chỉ encode 1 lần). Hàm `build_ffmpeg_command(video, options) -> list[str]` có unit test kiểm tra từng tổ hợp checkbox.
- Progress render: parse `-progress pipe:1` của ffmpeg để ra % thật.
- Trang chi tiết video: tab Original / Output để so sánh, nút tải output, nút mở thư mục.
- Preset render lưu trong Settings (ví dụ "Logo + sub", "Full").
- Dọn file tạm (`audio.wav`) sau khi xong.
- README: cách cài, cách chạy, cách bật cookies, cách update yt-dlp, troubleshooting.

**Done khi**
- Từ 1 link Douyin: Download → Transcribe+Dịch → TTS → Render, ra 1 file `output_final.mp4` có logo + phụ đề + giọng đọc, thao tác hoàn toàn trên UI.

## 7. Quy ước cho Claude Code

- Làm **từng phase**, báo kết quả và dừng chờ xác nhận trước khi sang phase tiếp theo.
- Mọi lệnh ffmpeg/yt-dlp chạy bằng `subprocess` với **list args, không dùng `shell=True`**, và validate/sanitize mọi input (URL, đường dẫn). Path của video luôn dựng từ `DATA_DIR` + id, không lấy path từ client. Chặn path traversal trên các endpoint file.
- Chỉ chấp nhận URL `http/https`.
- Timeout cho mỗi job; job lỗi phải ghi `error` đầy đủ (stderr rút gọn) chứ không nuốt lỗi.
- Không hard-code secret. Key Claude API đọc từ `.env`; thiếu key thì tính năng dịch báo lỗi rõ, các tính năng khác vẫn chạy.
- Type hint đầy đủ, `ruff` + `pytest`. Viết test cho: parse URL, build ffmpeg command, parse SRT, khớp timing TTS.
- Khi gặp quyết định chưa rõ, chọn phương án đơn giản nhất và ghi chú trong README thay vì hỏi lại.

## 8. Rủi ro đã biết

- **Douyin/Facebook đổi API thường xuyên** → yt-dlp có thể hỏng bất kỳ lúc nào; luôn có nút update và hiển thị lỗi gốc.
- **Whisper chậm khi chạy CPU** → mặc định model `small`, cho phép đổi `base`/`medium`; log thời gian xử lý.
- **Video Douyin có watermark chạy ngang** → không xử lý trong scope này, chỉ ghi chú.
- **Bản quyền**: tool chỉ để dùng cá nhân; user tự chịu trách nhiệm khi đăng lại nội dung.

## 9. Ngoài scope (để sau nếu cần)

- Nhận diện và che watermark gốc
- Nhiều engine TTS (ElevenLabs, FPT.AI, OpenAI) — chỉ cần giữ interface sẵn
- Batch render nhiều video cùng lúc
- Cắt/ghép clip, thêm nhạc nền