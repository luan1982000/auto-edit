# Phase 4 — Phụ đề (Whisper + DeepSeek + burn ASS)

- **Commit:** `d32f8d1` (base `198e199`)
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng (DeepSeek thật chưa test do thiếu key)
- **Tài liệu phase trước:** [phase-3.md](phase-3.md)

## Phạm vi đã làm

- Tách audio 16 kHz mono → `audio.wav`, luôn xoá sau transcribe.
- Nhận dạng bằng `faster-whisper` (model cấu hình trong Settings), cache model theo tên.
- Dịch toàn bộ segment bằng **DeepSeek** trong một request JSON, kiểm tra chặt response.
- Lưu `subtitle.json` (giữ bản nguồn) + `subtitle.srt`; API đọc/lưu để sửa.
- UI bảng phụ đề: sửa inline, thêm/xoá dòng, lưu, tạo phụ đề, tạo + dịch, dịch lại.
- Burn phụ đề bằng ASS (font/cỡ/vị trí, tự xuống dòng, viền, tiếng Việt có dấu).
- Render nhận thêm checkbox phụ đề, kết hợp logo + sub trong cùng một lệnh ffmpeg.

## File mới / thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/services/subtitles.py` | **Mới** — model, parse/format SRT, wrap, build/write ASS, load/save JSON |
| `backend/app/services/transcribe.py` | **Mới** — Protocol + `FasterWhisperTranscriber` |
| `backend/app/services/translate.py` | **Mới** — DeepSeek chat completions + parse JSON |
| `backend/app/routers/subtitles.py` | **Mới** — transcribe/translate/subtitle endpoints |
| `backend/app/worker.py` | Handler transcribe + translate, persist, cleanup, cờ `has_subtitle` |
| `backend/app/services/ffmpeg_utils.py` | Thêm `extract_audio` |
| `backend/app/services/render.py` | Thêm filter ASS |
| `backend/app/schemas.py` | Schema subtitle, transcribe, translate, validation |
| `backend/pyproject.toml` | Thêm `faster-whisper`, `httpx` |
| `frontend/src/components/SubtitleEditor.tsx` | **Mới** — bảng sửa phụ đề |
| `frontend/src/pages/VideoDetail.tsx` | Tích hợp editor, job transcribe/dịch, checkbox phụ đề |
| `frontend/src/api.ts` | API + type phụ đề |
| Tests | `test_subtitles`, `test_transcribe`, `test_translate`, `test_subtitle_api`, `test_worker_subtitles`, cập nhật render/ffmpeg |

## Transcribe

- `extract_audio`: `ffmpeg -map 0:a:0 -vn -ac 1 -ar 16000 -c:a pcm_s16le`; lỗi/empty → lỗi rõ.
- Model: `WhisperModel(model_name, device="auto", compute_type="int8")`, cache trong dict trên
  instance `FasterWhisperTranscriber`.
- `vad_filter=True`, `beam_size=5`.
- Segment rỗng bị bỏ; start/end được kẹp không âm, start ≤ end.
- Progress: 5% bắt đầu, 10–95% theo timestamp cuối segment / duration, 100% khi xong.
- Job params chụp `model`, `target_language`, `translate` tại thời điểm bấm.
- Nếu `translate=true`: transcribe xong lưu bản nguồn trước, sau đó mới dịch; dịch lỗi → job
  `failed` nhưng phụ đề nguồn vẫn còn.
- `audio.wav` được xoá trong `finally`, kể cả khi transcribe lỗi.

## Dịch bằng DeepSeek

- Endpoint: `{DEEPSEEK_BASE_URL}/chat/completions`, `Authorization: Bearer <key>`.
- Payload: `model`, `temperature=0.2`, `max_tokens=8000`, `response_format=json_object`.
- System prompt yêu cầu giữ nguyên số segment/thứ tự, không timestamp, trả
  `{"segments": [{"id": int, "text": str}]}`.
- User message chứa `target_language` + danh sách `{id, text}`.
- Response:
  - thiếu `choices` / content rỗng → `TranslationError`;
  - bóc code fence ```json``` nếu có;
  - yêu cầu đúng tập id `0..n-1`, không trùng, không rỗng, đủ số lượng;
  - giữ start/end gốc, chỉ thay text.
- Lỗi HTTP hiển thị status + 500 ký tự đầu của body; lỗi mạng được wrap.
- Thiếu key: `Chưa cấu hình DEEPSEEK_API_KEY trong .env — không thể dịch phụ đề`.
- Nếu ngôn ngữ nguồn trùng target: bỏ qua dịch, lưu bản nguồn, job done.
- "Dịch lại" dùng `source_segments` đã lưu, không dịch chồng lên bản dịch.

## Lưu trữ & API

- `subtitle.json`:
  ```json
  {
    "language": "zh",
    "target_language": "vi",
    "translated": true,
    "segments": [{"start": 0.0, "end": 1.2, "text": "..."}],
    "source_segments": [{"start": 0.0, "end": 1.2, "text": "..."}]
  }
  ```
- `subtitle.srt` luôn ghi từ `segments` hiện tại.
- `GET/PUT /api/videos/{id}/subtitle`; PUT thay toàn bộ danh sách, tối đa **2000 dòng**, text
  **1..1000 ký tự**, `end > start`, start ≥ 0, text được chuẩn hoá khoảng trắng.
- PUT bị chặn khi đang có job transcribe/translate (`409`); transcribe/translate cũng chặn lẫn
  nhau để tránh ghi đè.
- Job transcribe/translate yêu cầu video `ready` + file nguồn hợp lệ trong thư mục video.

## Burn ASS

- ASS sinh theo `video_width × video_height` (PlayResX/Y), nên đúng cả video dọc/ngang.
- Font lấy từ Settings; rỗng → `Arial`; tên font được làm sạch dấu phẩy/xuống dòng.
- Cỡ: `round(video_height * setting_size / 540)`, kẹp **12..200**.
- Vị trí: `bottom` (alignment 2), `center` (5), `top` (8); margin dọc 8% chiều cao, ngang 5%.
- Xuống dòng: **40 ký tự** nếu video dọc (`height > width`), **60** nếu ngang; từ quá dài bị cắt
  cứng; `\N` nối dòng.
- Style: chữ trắng, viền đen 2 px, bóng 1, `BorderStyle=1`, `ScaledBorderAndShadow=yes`.
- Escape `\`, `{`, `}` để tránh override ASS ngoài ý muốn.
- Khi render, worker ghi `subtitle.ass` vào thư mục video và chạy ffmpeg với `cwd` là thư mục đó;
  builder chỉ chấp nhận tên file dạng `[A-Za-z0-9_.-]+\.ass`, không nhận path từ client.

## UI

- Không có phụ đề: nút **Tạo phụ đề** / **Tạo + dịch**.
- Có phụ đề: badge ngôn ngữ nguồn → đích, trạng thái Đã dịch/Bản gốc, nút **Dịch sang VI**,
  **+ Dòng**, **Lưu phụ đề**, **Xoá** từng dòng.
- Sửa inline start/end/text; validate phía client trước khi gửi; dirty state chặn dịch lại và tạo
  voice.
- Nút transcribe sẽ hỏi xác nhận nếu đang có thay đổi chưa lưu.
- Polling video/job 2s cập nhật `has_subtitle`, tải lại phụ đề sau job done.

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| Unit/integration tests | 268 passed toàn bộ hiện tại; các file Phase 4 đều xanh |
| ffmpeg thật | extract audio, burn ASS và render kết hợp được test end-to-end với video tổng hợp |
| DeepSeek thật | **chưa chạy** — không có `DEEPSEEK_API_KEY`; mock HTTP test phủ success/401/JSON hỏng/thiếu segment |
| Whisper thật | **chưa chạy** trong test tự động (model nặng); transcriber được test qua fake, ffmpeg audio path test thật |

## Quyết định đã chốt

- Dùng DeepSeek thay Claude theo yêu cầu; vẫn giữ interface dễ thay provider.
- Chỉ gửi **một request** cho toàn bộ phụ đề như PLAN; với video rất dài có thể vượt `max_tokens`
  8000 — khi đó job lỗi rõ và người dùng có thể chia nhỏ video. Chưa chunk vì plan ưu tiên đơn giản.
- Lưu cả `source_segments` để **Dịch lại** không bị dịch lồng.
- ASS thay vì `subtitles` SRT vì cần style/font/xuống dòng; file nằm cùng thư mục video.
- Text phụ đề lưu một dòng, việc xuống dòng chỉ xảy ra khi render.
- Nếu dịch lỗi sau transcribe, giữ phụ đề nguồn thay vì rollback — người dùng không mất công
  nhận dạng và có thể thử dịch lại khi đã cấu hình key.
- `has_subtitle` bật ngay sau transcribe thành công, kể cả bước dịch sau đó lỗi.
