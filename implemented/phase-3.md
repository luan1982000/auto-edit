# Phase 3 — Logo overlay

- **Commit:** `198e199` (base `7467b7d`)
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng
- **Tài liệu phase trước:** [phase-2.md](phase-2.md)

## Phạm vi đã làm

- Upload logo trong Cài đặt kèm panel xem trước vị trí bằng CSS.
- Lưu logo an toàn trong `DATA_DIR/assets`, chỉ phục vụ file nằm trong thư mục này.
- Chỉnh góc (`tl/tr/bl/br`), kích thước theo % chiều rộng video, opacity và margin.
- `build_ffmpeg_command()` dựng lệnh overlay logo bằng list args, không shell.
- API render tạo job; worker render ra `output_final.mp4` qua file tạm.
- UI trang chi tiết có checkbox Logo và nút Render (Phase 3 mới bật Logo).

## File mới / thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/services/assets.py` | **Mới** — sniff magic bytes, lưu/xoá/resolve logo an toàn |
| `backend/app/services/render.py` | **Mới** — `LogoOptions`, `RenderOptions`, `build_ffmpeg_command` |
| `backend/app/routers/settings.py` | Thêm upload (multipart), xem, xoá logo |
| `backend/app/routers/editing.py` | **Mới** — `POST /api/videos/{id}/render` |
| `backend/app/worker.py` | Thêm render handler, probe video, progress, ghi output |
| `backend/app/services/ffmpeg_utils.py` | Thêm progress parser + `run_ffmpeg_with_progress` |
| `backend/app/main.py` | Include router editing |
| `backend/tests/test_render.py` | **Mới** — build lệnh, vị trí, opacity, scale, path |
| `backend/tests/test_logo_render_api.py` | **Mới** — upload/xem/xoá logo, validate render request |
| `backend/tests/test_worker_render.py` | **Mới** — render thật bằng ffmpeg với nguồn tổng hợp |
| `frontend/src/api.ts` | API upload/xoá logo, render, kiểu dữ liệu |
| `frontend/src/pages/Settings.tsx` | Khu vực Logo: upload, preview, các thông số |
| `frontend/src/pages/VideoDetail.tsx` | Player, checkbox Logo, nút Render, trạng thái job |

## Lưu và phục vụ logo

- Nhận PNG, JPEG, WEBP; tối đa **5 MB** (`MAX_LOGO_BYTES`).
- Loại file xác định bằng **magic bytes**, không tin `Content-Type` hay đuôi file:
  - PNG `\x89PNG\r\n\x1a\n`
  - JPEG `\xff\xd8\xff`
  - WEBP `RIFF....WEBP`
- Ghi atomically vào `DATA_DIR/assets/logo.<ext>` qua file tạm, sau đó xoá các `logo.*` cũ.
- `resolve_logo()` chỉ chấp nhận path resolve nằm trong `assets_dir`, là file thật và vẫn có magic
  bytes ảnh; path lạ/không hợp lệ trả `None`.
- `GET /api/settings/logo` trả `404` nếu chưa có logo; `DELETE` xoá cả record lẫn file.

## Overlay

Filter logo:

```
[1:v]scale=<width>:-2,format=rgba,colorchannelmixer=aa=<opacity>[logo];
[0:v][logo]overlay=<x>:<y>[vout]
```

- `width = round(video_width * scale_pct / 100)`, làm tròn xuống số chẵn (yuv420p), tối thiểu 2 px.
- `scale=width:-2` giữ tỉ lệ logo.
- Opacity `0..1`; margin `>= 0`.
- Toạ độ:
  - trái: `margin`, phải: `main_w-overlay_w-margin`
  - trên: `margin`, dưới: `main_h-overlay_h-margin`
- Video dọc 1080×1920 và video ngang đều dùng cùng công thức theo chiều rộng.

## Render

- Chỉ một input video gốc + input logo, một `-filter_complex`.
- Output: `output_final.tmp.mp4` → `replace` thành `output_final.mp4` sau khi ffmpeg thành công.
- Video `libx264 -crf 20 -preset medium -pix_fmt yuv420p -movflags +faststart`.
- Chưa có voice nên audio được `-map 0:a? -c:a copy`.
- Progress đọc `-progress pipe:1`; parser chấp nhận `out_time_us`/`out_time_ms`/`out_time`.
- Timeout `max(300s, duration * 10)`; lỗi ffmpeg được rút gọn 8 dòng cuối, ghi vào `job.error`.
- Không bao giờ dùng `original.mp4` làm output; builder từ chối nếu input/output resolve trùng nhau.

## UI

- **Cài đặt → Logo**: upload, xoá, preview 16:9 mô phỏng góc/kích thước/độ mờ; form lưu qua
  `PUT /api/settings`.
- **Trang video**: tab Original/Output, checkbox Logo (disabled nếu chưa upload), nút Render, job
  card hiện progress. Sau khi render xong, output được cache-bust và chọn tab Output.
- Phase 3 chỉ bật checkbox Logo; checkbox phụ đề/voice được thêm ở Phase 4–5 nhưng builder đã sẵn
  sàng nhận các filter đó.

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `pytest` (toàn bộ tại thời điểm hiện tại) | 268 passed |
| `ruff check app tests` | All checks passed |
| `npm run build` | OK |
| Render thật | Video nguồn 640×360 + logo PNG, ffmpeg exit 0, output có video/audio |

Test Phase 3 hiện có:

- `test_render.py`: vị trí 4 góc, scale theo chiều rộng, opacity, margin, tên file subtitle, audio
  mode, chống ghi đè original, mọi tổ hợp checkbox (bổ sung ở Phase 6).
- `test_logo_render_api.py`: upload định dạng hợp lệ/không hợp lệ, giới hạn 5 MB, xem/xoá logo,
  render khi thiếu logo, validate request.
- `test_worker_render.py`: render thật bằng ffmpeg (logo, phụ đề, voice ở các phase sau).

## Quyết định đã chốt

- Dùng `scale=<width>:-2` thay vì `scale2ref` như gợi ý trong PLAN: kích thước video đã biết từ
  ffprobe, công thức đơn giản hơn và tránh phụ thuộc thứ tự filter graph.
- Logo không bắt buộc phải là PNG; chấp nhận JPEG/WEBP nếu magic bytes hợp lệ.
- Chỉ lưu **một** logo tại một thời điểm; upload mới thay logo cũ.
- Render dùng output tạm + `replace` để không bao giờ để lại file hỏng và không chạm bản gốc.
- Phase 3 giữ `-c:a copy`; encode AAC chỉ bật khi có voice (Phase 5).
