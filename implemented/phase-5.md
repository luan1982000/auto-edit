# Phase 5 — Giọng đọc (edge-tts) + mix audio

- **Commit:** `41955d1` (base `d32f8d1`)
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng bằng edge-tts thật
- **Tài liệu phase trước:** [phase-4.md](phase-4.md)

## Phạm vi đã làm

- Interface `TTSEngine` + engine **edge-tts**, validate voice/rate.
- Sinh audio cho từng segment phụ đề, tăng tốc tối đa 1.4x nếu dài hơn khung.
- Ghép timeline bằng `adelay` + `amix`, đệm im lặng, giới hạn biên độ → `voice.mp3`.
- Job TTS có progress theo từng segment, timeout, lỗi rõ; voice cũ được giữ nếu job fail.
- API nghe thử một câu (MP3) và tạo voice; settings giọng/tốc độ có validation.
- Render thêm voice với 3 chế độ âm thanh gốc: `mute`, `duck`, `keep`.
- UI chọn giọng/tốc độ, nghe thử, tạo/tạo lại giọng, tự bật voice + duck khi vừa tạo xong.

## File mới / thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/services/tts.py` | **Mới** — engine, validate, atempo, timeline builder |
| `backend/app/routers/tts.py` | **Mới** — `POST /videos/{id}/tts`, `POST /tts/preview` |
| `backend/app/worker.py` | Thêm `build_tts_handler`, `_set_has_voice`, cập nhật render handler |
| `backend/app/services/render.py` | Thêm voice input, filter audio 3 chế độ, encode AAC |
| `backend/app/services/ffmpeg_utils.py` | Thêm `probe_audio_duration`, `has_audio` trong `probe_video` |
| `backend/app/schemas.py` | `TtsRequest`, `TtsPreviewRequest`, validate settings |
| `backend/app/models.py` | `has_voice` dùng sẵn từ Phase 1 (không đổi schema) |
| `frontend/src/lib/voices.ts` | **Mới** — danh sách giọng/tốc độ/label |
| `frontend/src/components/VoicePanel.tsx` | **Mới** — UI TTS |
| `frontend/src/pages/VideoDetail.tsx` | Tích hợp VoicePanel, preview, generate, auto-enable voice |
| `frontend/src/api.ts` | `generateVoice`, `previewTts` |
| Tests | `test_tts` (27), `test_tts_api` (9), `test_worker_tts` (6), bổ sung render/ffmpeg |

## Edge TTS

- `EdgeTTSEngine.synthesize(text, voice, rate, out_path)`:
  - chuẩn hoá text (gộp khoảng trắng), từ chối rỗng;
  - validate `voice` bằng regex `[A-Za-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z0-9]+Neural`;
  - validate `rate` bằng `[+-]\d{1,3}%`;
  - xoá output cũ, tạo thư mục;
  - chạy `edge_tts.Communicate(...).save()` trong event loop mới bằng `asyncio.run`;
  - bao toàn bộ lỗi thành `TTSError("edge-tts lỗi: ...")`, timeout mặc định 60s;
  - kiểm tra file tồn tại và không rỗng, nếu không thì xoá + báo lỗi.
- Factory có thể inject để test, không gọi mạng trong unit test.

## Timeline voice

- Mỗi segment không rỗng sinh `tts/seg-0000.mp3`, probe duration thật.
- `compute_atempo(audio, available)`:
  - audio ≤ available → `1.0`;
  - ngược lại `min(round(audio/available, 3), 1.4)`.
- Nếu vẫn dài hơn sau khi cap 1.4x thì chấp nhận tràn nhẹ sang khoảng trống kế tiếp.
- Filter mỗi clip: `[i:a]atempo=X,adelay=<start_ms>|<start_ms>[ai]` (bỏ `atempo` nếu 1.0).
- Nhiều clip:
  `amix=inputs=n:duration=longest:normalize=0:dropout_transition=0`.
- Sau mix: `apad,alimiter=limit=0.95`, cắt `-t <duration video>`.
- Encode MP3 `libmp3lame -q:a 4`.
- Ghi `voice.tmp.mp3`, chỉ `replace` thành `voice.mp3` khi toàn bộ thành công; thư mục `tts/` và
  file tạm được dọn trong `finally`/`except`.
- Video duration ≤ 0 → lấy `max(end)` của segment.

## Job TTS

- Yêu cầu video `ready`, file nguồn hợp lệ, `subtitle.json` có ít nhất một dòng có chữ.
- Chặn job TTS đang chạy khác trên cùng video (`409`).
- Voice/rate được snapshot vào `job.params` lúc bấm; ưu tiên payload, sau đó Settings.
- Progress: 5% + `index/total * 75` khi từng segment, 85% khi ghép, 100% khi xong.
- Deadline được kiểm tra trước/sau mỗi segment.
- Lỗi ở bất kỳ segment nào → job `failed`, `voice.mp3` cũ (nếu có) giữ nguyên, `has_voice` không
  đổi thành false.
- Thành công → `has_voice = true`.

## Nghe thử

- `POST /api/tts/preview` body `{text, voice, rate}`; text **1..1000 ký tự**, chuẩn hoá khoảng
  trắng, voice/rate bắt buộc và validate.
- Trả `audio/mpeg`, `Cache-Control: no-store`; file tạm `assets/tts_preview.mp3`.
- Lỗi edge-tts → `502` kèm message, xoá file.
- UI lấy câu đầu tiên chưa lưu trong bảng phụ đề (kể cả chỉnh sửa chưa save) để nghe thử; phát
  bằng `Audio` từ Blob URL, dừng/revoke khi đổi câu hoặc unmount.

## Render audio

`RenderOptions` thêm `voice_path`, `audio_mode`, `has_original_audio`:

| Mode | Filter |
|---|---|
| `mute` | `[voice:a]alimiter=limit=0.95[aout]` |
| `keep` | `[0:a]volume=1[orig];[voice:a]anull[voice];[orig][voice]amix=inputs=2:duration=longest:normalize=0:dropout_transition=0,alimiter=limit=0.95[aout]` |
| `duck` | như `keep` nhưng `volume=0.2` |

- `DUCK_VOLUME = 0.2`.
- Nếu video gốc không có audio (`probe_video()["has_audio"] == False`) → dùng nhánh voice-only cho
  cả `mute` và `duck`, tránh filter tham chiếu stream không tồn tại.
- Có voice → audio AAC 192 kbps; không voice → `-c:a copy`.
- Voice input được thêm sau logo; index input tính động.
- `anull` giữ voice là một stream liên tục trước `amix`; `duration=longest` + `apad` (khi tạo
  voice) đảm bảo không cắt mất tiếng và không treo.
- Render handler kiểm tra `voice.mp3` tồn tại và probe audio gốc trước khi dựng lệnh.

## UI

- `VoicePanel`: chọn **HoaiMy (nữ)** / **NamMinh (nam)**, tốc độ Chậm 20% … Nhanh 20%.
- Badge “Đã có voice.mp3” / “Chưa tạo giọng”; nút **Nghe thử**, **Tạo giọng đọc** / **Tạo lại**.
- Sửa phụ đề chưa lưu → chặn tạo voice, hiện gợi ý lưu trước.
- Voice/rate khởi tạo từ Settings nhưng không ghi đè sau khi người dùng đã chỉnh.
- Khi `has_voice` chuyển false → true, app tự bật checkbox voice + `duck`; nếu preset đang là
  `Logo` / `Logo + phụ đề` và trang chưa bị chỉnh tay, bước áp preset ngay sau đó sẽ tắt lại voice.

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| Unit/integration | `test_tts` 27, `test_tts_api` 9, `test_worker_tts` 6 — xanh |
| ffmpeg thật | timeline 2 clip ra đúng độ dài; render 3 mode với logo + sub + voice |
| edge-tts thật | 2 segment → `voice.mp3` 6.05s / 31.532 bytes cho video 6.0s |
| Render smoke | logo + ASS + voice (`duck`) trong 1 lệnh ffmpeg → output 6.01s có audio |
| Toàn bộ suite hiện tại | 268 passed; ruff clean; frontend build OK |

**Chưa kiểm chứng:** edge-tts với video rất dài / nhiều segment (giới hạn mạng, rate limit của
Microsoft) và nghe cảm quan chất lượng ducking trên nhiều loại video thật.

## Quyết định đã chốt

- Dùng `asyncio.run` trong worker thread thay vì thêm async worker: edge-tts chỉ cần một event loop
  ngắn cho mỗi segment, giữ worker đồng bộ và dễ test.
- Giữ voice cũ khi tạo lại thất bại; không đặt `has_voice=false` để tránh mất trạng thái render.
- `atempo` cap 1.4x đúng PLAN; không cắt audio vì sẽ mất chữ.
- Ducking bằng `volume=0.2` thay vì sidechaincompress: ổn định, dễ test, đúng tinh thần “giảm còn
  ~20%” trong PLAN.
- Dùng `anull` thay vì `apad` trên voice trong lúc mix; `amix=duration=longest` kết hợp voice đã
  `apad` và `-t` của render xử lý độ dài.
- Preview dùng chung một file tạm trong `assets/` vì app local một người dùng; request sau ghi đè
  request trước.
