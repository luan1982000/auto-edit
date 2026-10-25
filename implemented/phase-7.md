# Phase 7 — Che phụ đề cũ + chọn ngôn ngữ (bổ sung)

- **Commit code:** `58be7e5`
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng
- **Tài liệu phase trước:** [phase-6.md](phase-6.md)

## Phạm vi đã làm

- Tạo phụ đề mới **ghi đè lên phụ đề cũ đã burn trong video** bằng một vùng che đen chọn tay.
- Trước khi transcribe, chụp **3 ảnh mẫu** (15% / 50% / 85% thời lượng) để người dùng thấy đúng
  vị trí phụ đề hiện tại trên chính video đó.
- Cho chọn **ngôn ngữ nguồn** cho Whisper và **ngôn ngữ đích** cho DeepSeek ngay trong hộp thoại
  tạo phụ đề; mỗi lần dịch lại cũng chọn được ngôn ngữ đích.
- Thêm nút **Tạo lại phụ đề** cho video đã có phụ đề: mở lại hộp thoại nhận dạng (chọn ngôn
  ngữ/vùng che/dịch) và xác nhận trước khi thay toàn bộ dữ liệu hiện tại.
- Sửa ba lỗi phát hiện ở vòng review cuối:
  - output render lần thứ hai trở đi không cập nhật trong player/download;
  - job `running` bị kẹt sau khi app khởi động lại;
  - thiếu/hỏng `yt-dlp` làm app không khởi động được.

## Luồng che phụ đề cũ

### 1. Chụp ảnh mẫu

`POST /api/videos/{id}/sample-frames`:

1. Kiểm tra video tồn tại, trạng thái `ready`, file nguồn còn trên đĩa.
2.`ffprobe` lấy thời lượng, chọn các mốc `0.15 / 0.5 / 0.85` (kẹp trong khoảng hợp lệ).
3. Mỗi mốc chạy một lệnh ffmpeg riêng, xuất JPEG rộng tối đa **720 px** vào
   `videos/{id}/frames/sample-N.jpg`; file cũ trong thư mục được dọn trước khi chụp.
4. Trả `{frames: [{time, url}], region}`; `region` là vùng che đã lưu (nếu có).

`GET /api/videos/{id}/frames/{name}` chỉ phục vụ tên khớp `sample-[1-9][0-9]*.jpg`, kiểm tra
containment trong thư mục video, trả `Cache-Control: no-store` để lần chụp sau không bị ảnh cũ.

### 2. Chọn vùng

`FrameRegionPicker` hiển thị 3 thumbnail + một ảnh lớn. Người dùng có thể:

- kéo chuột để vẽ hình chữ nhật trên ảnh (pointer capture, toạ độ chuẩn hoá);
- dùng preset **Dải dưới** / **Dải trên** / **Giữa khung**;
- chọn **Không che** để xoá vùng;
- xem toạ độ `x, y, width, height` theo tỉ lệ `0..1`.

Vùng mặc định khi chưa lưu là dải dưới `x=0.05, y=0.78, w=0.9, h=0.15` — vị trí phổ biến của phụ
đề TikTok/Reels/Douyin. Diện tích tối thiểu 1% mỗi chiều; schema backend chặn toạ độ âm, kích
thước không dương, vượt quá `1.0`, `NaN`/`Infinity`.

### 3. Lưu và render

- `PUT /api/videos/{id}/cover-region` lưu nguyên tử vào `videos/{id}/cover_region.json`;
  `DELETE` xoá file; `GET` trả `null` nếu chưa có.
- Khi bấm bắt đầu trong hộp thoại, frontend lưu (hoặc xoá) vùng trước rồi mới tạo job
  transcribe/translate. Transcribe không phụ thuộc vào vùng che; vùng chỉ dùng lúc render.
- Worker render chỉ đọc `cover_region.json` khi checkbox **Phụ đề** bật. Toạ độ được đổi sang
  pixel theo kích thước thật của video và thêm filter đầu tiên trong chuỗi video:

```text
[0:v]drawbox=x=X:y=Y:w=W:h=H:color=black@1.0:t=fill[vcover];
[vcover][1:v]overlay=... [vlogo];
[vlogo]ass=subtitle.ass[vout]
```

- `drawbox` phủ **đen đặc** trước logo và phụ đề mới, nên phụ đề cũ bị che hoàn toàn; logo vẫn nằm
  trên vùng che nếu người dùng đặt logo ở đó. Video gốc không bị sửa.
- File JSON hỏng hoặc toạ độ ngoài biên làm job render `failed` với thông báo
  `Vùng che phụ đề cũ không hợp lệ: ...` thay vì âm thầm che sai vùng.
- Render chỉ logo (không bật phụ đề) bỏ qua vùng che — tránh một dải đen không mong muốn.

## Chọn ngôn ngữ

- Whitelist nguồn gồm 24 mã Whisper có nhãn tiếng Việt; `""`, `auto`, `null` đều có nghĩa là
  **Tự động nhận dạng**. Chỉ khi người dùng chọn mã cụ thể thì tham số `language` mới được truyền
  vào faster-whisper.
- Whitelist đích gồm 24 mã trên cộng `zh-Hant` (Trung Phồn thể) — Whisper chỉ có một mã tiếng
  Trung nên `zh-Hant` chỉ dùng làm đích dịch.
- Mã được trim, so khớp không phân biệt hoa/thường và trả về mã chuẩn (`" ZH-HANT "` →
  `"zh-Hant"`). Mã ngoài danh sách bị `422` với thông báo rõ; dịch thiếu ngôn ngữ đích dùng giá
  trị trong Settings.
- Hộp thoại có 3 chế độ:
  - **Tạo phụ đề**: chọn ngôn ngữ nguồn + vùng che, không dịch;
  - **Tạo + dịch**: chọn cả nguồn, đích và vùng che;
  - **Dịch phụ đề** / **Vùng che**: chỉ dịch lại từ `source_segments` hoặc chỉ lưu vùng.
- Khi video đã có phụ đề, nút **Tạo lại phụ đề** dùng lại chế độ transcribe (có checkbox dịch),
  kèm xác nhận vì job mới ghi đè `subtitle.json` và thay cả bản đã sửa.
- Trang **Cài đặt** đổi ô ngôn ngữ đích từ text tự do sang `<select>` cùng danh sách, tránh gửi
  mã không hỗ trợ.
- DeepSeek vẫn đọc key từ `.env`; thiếu key chỉ làm job dịch lỗi, transcribe và render vẫn chạy.

## Ba lỗi review đã sửa

### Output_version

`VideoRead.output_version` là `st_mtime_ns` của `output_final.mp4` (0 nếu chưa có). Frontend so
sánh version giữa các lần poll; khi đổi, player đổi `?v=` và key để buộc tải bản mới, đồng thời
chuyển sang tab Output. Cách này đúng cho mọi lần render, kể cả render lại cùng nội dung.

### Job mồ côi sau khởi động lại

`JobWorker.start()` gọi `recover_orphaned_jobs()` trước khi chạy vòng lặp:

- job còn `running` từ tiến trình cũ → `failed` với lý do
  `Job bị gián đoạn do ứng dụng khởi động lại — hãy chạy lại.`;
- video `downloading` không còn job `pending`/`running` → `failed` với lý do
  `Tải xuống bị gián đoạn — hãy tải lại video.`;
- video `ready` và job đang chờ hợp lệ không bị đụng tới.

### yt-dlp import lazy

Bỏ `import yt_dlp` ở cấp module trong router system và downloader. Thiếu package:

- app vẫn khởi động, `/api/health` trả `yt_dlp: false` và `problems`;
- job download báo `Chưa cài yt-dlp — không tải được video. Cài bằng: python -m pip install yt-dlp`.

## API mới / thay đổi

| Method | Endpoint | Ghi chú |
|---|---|---|
| POST | `/api/videos/{id}/sample-frames` | Chụp 3 ảnh mẫu, trả `frames` + `region` đã lưu |
| GET | `/api/videos/{id}/frames/{name}` | Chỉ `sample-N.jpg`, `no-store`, chặn traversal |
| GET/PUT/DELETE | `/api/videos/{id}/cover-region` | Đọc/lưu/xoá vùng che `{x,y,width,height}` |
| POST | `/api/videos/{id}/transcribe` | Thêm `source_language`, `target_language` |
| GET | `/api/videos/{id}` | Thêm `output_version` |

## File mới / thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/services/cover.py` | **Mới** — `CoverRegion`, validate, đọc/ghi JSON nguyên tử |
| `backend/app/services/languages.py` | **Mới** — whitelist nguồn/đích + chuẩn hoá mã |
| `backend/app/services/ffmpeg_utils.py` | `extract_sample_frames()` chụp ảnh theo mốc thời gian |
| `backend/app/services/render.py` | `RenderOptions.cover_region`, filter `drawbox` đầu chuỗi video |
| `backend/app/services/transcribe.py` | Nhận `language` tuỳ chọn |
| `backend/app/services/downloader.py` | Import yt-dlp lazy, lỗi cài đặt rõ ràng |
| `backend/app/models.py` | Thuộc tính `Video.output_version` |
| `backend/app/schemas.py` | Schema vùng che, ảnh mẫu, validate ngôn ngữ, `output_version` |
| `backend/app/routers/subtitles.py` | API ảnh mẫu, phục vụ frame, CRUD vùng che, tham số ngôn ngữ |
| `backend/app/routers/system.py` | Import yt-dlp lazy |
| `backend/app/worker.py` | Truyền ngôn ngữ, đọc vùng che, phục hồi job mồ côi |
| `backend/tests/test_cover.py` | **Mới** — 14 test validate/round-trip/lỗi JSON |
| `backend/tests/test_frames.py` | **Mới** — ffmpeg chụp ảnh thật, dọn ảnh cũ |
| `backend/tests/test_languages.py` | **Mới** — whitelist + chuẩn hoá |
| `backend/tests/test_subtitle_region_api.py` | **Mới** — API ảnh mẫu/vùng che/traversal |
| `backend/tests/test_system.py` | **Mới** — app vẫn chạy khi thiếu yt-dlp |
| `backend/tests/test_*` | Cập nhật render, transcribe, subtitle API, worker, API |
| `frontend/src/lib/languages.ts` | **Mới** — nhãn ngôn ngữ dùng chung |
| `frontend/src/components/FrameRegionPicker.tsx` | **Mới** — chọn vùng trên ảnh mẫu |
| `frontend/src/components/SubtitleSetupDialog.tsx` | **Mới** — hộp thoại ngôn ngữ + vùng che |
| `frontend/src/components/SubtitleEditor.tsx` | Badge vùng che, nút mở hộp thoại mới |
| `frontend/src/pages/VideoDetail.tsx` | Tải vùng che, điều phối dialog/job, cache-bust output |
| `frontend/src/pages/Settings.tsx` | Ngôn ngữ đích dạng select |
| `frontend/src/api.ts` | Type + gọi API mới, `output_version` |

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `pytest -o addopts="" -q` | **342 passed** trong 12.28s |
| `ruff check app tests` | All checks passed |
| `npm run build` | OK — CSS 46.93 kB, JS 334.01 kB (gzip 8.73 / 100.40 kB) |
| Ảnh mẫu + render | Test dùng ffmpeg thật cho extract frame; filter graph cover có unit test riêng |
| Dữ liệu thật | `data/` chỉ được đọc (kiểm tra settings), không xoá/sửa |

Phân bổ test mới/đã tăng: `test_cover` 14, `test_languages` 12, `test_subtitle_region_api` 9,
`test_frames` 3, `test_system` 2; `test_render` 31 → 42, `test_subtitle_api` 10 → 15,
`test_worker` 14 → 19, `test_downloader` 10 → 11.

**Chưa kiểm chứng end-to-end:**

- Mở trình duyệt chạy tay toàn bộ luồng: tải video thật → chụp ảnh → kéo vùng → transcribe →
  render → xem output.
- Gọi DeepSeek API thật (không có key trong phiên test) và tải link Douyin thật.
- Cảm giác kéo/thả vùng trên ảnh được test qua API + logic toạ độ, chưa có browser automation.

## Hạn chế đã biết (deferred)

- `target_language` cũ trong DB (từ ô text tự do trước đây) không được migrate; giá trị lạ có thể
  khiến form Settings không lưu được cho tới khi người dùng chọn lại. DB thực tế của phiên này
  đang là `vi` nên không ảnh hưởng.
- Settings nhận JSON `null` tường minh cho vài trường có thể trả 500 thay vì 422.
- DeepSeek trả JSON không phải object có thể gây `AttributeError` thay vì lỗi job gọn.
- Sửa phụ đề trong lúc TTS/render đang chạy không làm voice cũ mất hiệu lực; lần render đó vẫn
  dùng voice đã sinh.
- Job transcribe/dịch lỗi có thể để lại editor đang hiển thị dữ liệu cũ.
- Upload/xoá logo làm mất các thay đổi Settings chưa lưu trên form.
- Tự xuống dòng ASS là ước lượng ký tự; câu rất dài có thể tràn khung.
- Chưa xử lý rotation/SAR của video nguồn khi tính vùng che và overlay.
- Deadline job không cắt được ngay lúc ffmpeg đang render timeline hoặc bị treo không phát progress.
- `audio.wav` có thể còn lại nếu bước trích audio lỗi giữa chừng.
- `BIND_HOST` / `BIND_PORT` có trong `.env.example` nhưng Makefile/uvicorn không dùng.
- README TTS preview ghi voice/rate là tuỳ chọn trong khi API yêu cầu đủ trường.
- Test migration DB dùng bảng tối giản, chưa mô phỏng DB thật đầy đủ.
- Chưa có chọn file font cụ thể; chỉ nhập tên font hệ thống.

## Remotion

**Chưa tích hợp.** Với nhu cầu hiện tại (logo tĩnh, phụ đề ASS, voice theo timeline, render một
pass), ffmpeg nhanh hơn và ít dependency hơn. Remotion v4 (`@remotion/renderer`) cần Node +
Chromium, bundle webpack và một renderer thứ hai; nó không tự xoá phụ đề cũ — vẫn phải có vùng che
như đã làm. Remotion đáng cân nhắc khi cần phụ đề động/karaoke theo từng chữ, hiệu ứng chuyển
cảnh, template React và preview bằng `@remotion/player`; lúc đó nên thêm pipeline riêng có cờ bật,
giữ ffmpeg cho render cơ bản. Giấy phép Remotion miễn phí cho cá nhân và tổ chức ≤ 3 người; tổ
chức lớn hơn cần license thương mại.

## Quyết định đã chốt

- Chọn vùng che bằng **mắt người** trên ảnh mẫu thay vì OCR/vision: không thêm model, không đoán
  sai, và người dùng kiểm soát chính xác vùng bị phủ.
- Vùng che chỉ áp dụng khi render **có phụ đề**; render logo-only giữ nguyên khung hình.
- Toạ độ lưu chuẩn hoá `0..1` để đổi độ phân giải/render preset không làm lệch vùng.
- JSON vùng che hỏng → fail render rõ ràng, không fallback im lặng.
- Danh sách ngôn ngữ cố định (whitelist) thay vì nhận mã tuỳ ý; `zh-Hant` chỉ có ở đích dịch.
- Ngôn ngữ nguồn `auto` được biểu diễn bằng `null`/chuỗi rỗng, không truyền tham số cho Whisper.
- Cache-bust bằng `mtime_ns` của output thay vì đếm job, vì job có thể thất bại hoặc bị dọn.
- Job mồ côi bị đánh `failed` thay vì tự chạy lại: transcribe/render có thể tốn nhiều phút và
  người dùng cần biết trạng thái thật.
- yt-dlp import lazy để lỗi cài đặt hiện trong UI thay vì làm chết ứng dụng.
