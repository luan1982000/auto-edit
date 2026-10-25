# Phase 6 — Render gộp + hoàn thiện

- **Commit code:** `c0805cf` (base `41955d1`)
- **Commit tài liệu:** `1e9e2e9`
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng
- **Tài liệu phase trước:** [phase-5.md](phase-5.md)

## Phạm vi đã làm

- Render logo + phụ đề + voice trong **một lệnh ffmpeg duy nhất** (encode một lần).
- Unit test cho **cả 8 tổ hợp** checkbox Logo / Phụ đề / Voice.
- Preset render lưu trong Settings: `logo`, `logo_subtitle`, `full`.
- Migration idempotent cho DB cũ thêm cột `render_preset`.
- UI Settings chọn preset; trang video áp preset làm mặc định.
- Rà soát và hoàn thiện các yêu cầu Phase 6 đã có từ trước: progress thật, tab Original/Output,
  tải output, mở thư mục, dọn file tạm, README/tài liệu.

## File mới / thay đổi trong commit Phase 6

| File | Thay đổi |
|---|---|
| `backend/app/models.py` | Thêm `AppSettings.render_preset = "full"` |
| `backend/app/db.py` | `_migrate_settings()` thêm cột bằng `ALTER TABLE` nếu thiếu |
| `backend/app/schemas.py` | `RenderPreset` Literal, validate Settings |
| `backend/tests/test_db.py` | **Mới** — DB cũ được migrate, giá trị mặc định `full` |
| `backend/tests/test_api.py` | Kiểm tra preset mặc định, update hợp lệ/không hợp lệ |
| `backend/tests/test_render.py` | Test 8 tổ hợp checkbox |
| `frontend/src/api.ts` | Type `render_preset` |
| `frontend/src/pages/Settings.tsx` | Section **Preset render** |
| `frontend/src/pages/VideoDetail.tsx` | Áp preset vào checkbox/audio mode mặc định |

Các phần đã có từ phase trước và được xác nhận lại ở Phase 6:

- `build_ffmpeg_command()` gộp mọi filter vào một `-filter_complex`, một output tạm.
- `run_ffmpeg_with_progress()` parse `-progress pipe:1` thành % thật.
- Tab **Original / Output**, nút tải output (dùng endpoint file hỗ trợ Range), nút mở thư mục.
- `audio.wav` bị xoá sau transcribe; `tts/`, `voice.tmp.mp3`, `output_final.tmp.mp4` được dọn khi
  lỗi.
- README đầy đủ hướng dẫn cài/chạy/cookies/update yt-dlp/troubleshooting.

## Preset

| Preset | Logo | Phụ đề | Voice | Audio mode |
|---|---|---|---|---|
| `logo` | bật nếu có logo | tắt | tắt | `keep` |
| `logo_subtitle` | bật nếu có logo | bật nếu có phụ đề | tắt | `keep` |
| `full` | bật nếu có logo | bật nếu có phụ đề | bật nếu có voice | `duck` |

- Preset chỉ áp khi người dùng **chưa tự đổi checkbox** trên trang video (`optionsTouched=false`).
- Preset được áp lại khi settings/video thay đổi trong lúc chưa touched, nên sau khi transcribe
  hoặc tạo voice xong các checkbox tự cập nhật đúng.
- Vừa tạo voice xong: app tự bật voice + `duck` để render nhanh.
- Nếu video chưa có thành phần tương ứng, checkbox tương ứng vẫn tắt/disabled.

## Migration DB

`SQLModel.metadata.create_all()` không thêm cột vào bảng đã tồn tại. Vì vậy `init_db()` chạy
`_migrate_settings()`:

```sql
PRAGMA table_info(settings);
-- nếu bảng tồn tại và thiếu render_preset:
ALTER TABLE settings ADD COLUMN render_preset VARCHAR NOT NULL DEFAULT 'full';
```

- Idempotent: chạy lại không lỗi.
- DB mới do `create_all` đã có cột → bỏ qua ALTER.
- DB cũ có settings → nhận `'full'` cho dòng hiện có.
- Test `test_db.py` tạo bảng settings tối giản, chạy `init_db`, xác nhận cột + giá trị.

## Kiểm tra 8 tổ hợp

`test_every_checkbox_combination_builds_one_ffmpeg_command` dùng
`itertools.product([False, True], repeat=3)` và assert:

- luôn đúng **một** lệnh ffmpeg;
- `-filter_complex` chỉ xuất hiện khi có ít nhất một filter (và chỉ một lần);
- input logo/voice chỉ có khi checkbox bật;
- filter ASS chỉ có khi phụ đề bật;
- map `[vout]` khi có filter video, ngược lại `0:v:0`;
- map `[aout]` + AAC khi có voice; không voice thì `0:a?` + `copy`;
- luôn có `-progress pipe:1`;
- output là phần tử cuối.

## Progress, output, dọn tạm

- Render handler: `ctx.update(1, "Bắt đầu render...")`, sau đó map % ffmpeg vào `1..99`, cuối cùng
  100%.
- ffmpeg chạy với `cwd` là thư mục video (ASS dùng đường dẫn tương đối).
- Timeout `max(300s, duration * 10)` + deadline job.
- Lỗi: xoá `output_final.tmp.mp4`, giữ `output_final.mp4` cũ, job ghi stderr rút gọn 8 dòng cuối.
- Thành công: `replace` output tạm, set `has_output=true`.
- Nếu chọn render không có logo/phụ đề/voice, vẫn render được (video re-encode, audio copy), phù
  hợp test tổ hợp toàn false.

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `pytest` | **268 passed** |
| `ruff check app tests` | All checks passed |
| `npm run build` | OK — CSS 43.92 kB, JS 318.59 kB |
| Smoke render gộp | logo + ASS + voice thật, output 6.01s, 640×360, có audio, progress tới 100% |
| Smoke TTS | edge-tts thật, 2 segment, `voice.mp3` 6.05s |
| Bản gốc | không bị ghi đè; output ghi qua file tạm |

**Chưa kiểm chứng end-to-end UI với link Douyin thật** vì phiên test không có link/cookies. Các
thành phần đã test riêng và smoke bằng ffmpeg/edge-tts thật; DeepSeek chưa gọi thật do thiếu API
key.

## Quyết định đã chốt

- Preset chỉ là **mặc định khởi tạo**, không khóa lựa chọn người dùng; giữ UI linh hoạt.
- Lưu preset dạng chuỗi trong bảng settings hiện có thay vì bảng mới; migration đơn giản.
- Không thêm preset tùy biến (số lượng checkbox nhỏ, preset cố định đủ dùng theo PLAN).
- Giữ một lệnh ffmpeg duy nhất cho mọi tổ hợp, kể cả tổ hợp rỗng, để hành vi và test nhất quán.
- Tài liệu `implemented/` được đưa vào git từ Phase 6 để lịch sử triển khai đi cùng code.
