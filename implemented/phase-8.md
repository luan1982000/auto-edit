# Phase 8 — Upload video từ máy (bổ sung)

- **Commit code:** `58be7e5`
- **Trạng thái:** ✅ hoàn tất, đã kiểm chứng
- **Tài liệu phase trước:** [phase-7.md](phase-7.md)

## Phạm vi đã làm

- Thêm ô **Hoặc tải video từ máy** ngay dưới input download ở trang chủ.
- Chọn file hoặc kéo thả video có sẵn; giới hạn **2 GB**, có hiển thị tên/dung lượng file đã chọn.
- Backend lưu file an toàn, chuẩn hoá về `original.mp4`, tạo thumbnail + `meta.json` và thêm video
  `ready` vào thư viện ngay (không qua job).
- Video upload hiển thị nhãn nền tảng **Tải lên**; trang chi tiết không còn link nguồn rỗng mà ghi
  **Video tải lên từ máy**.

## Luồng backend

`POST /api/upload` (multipart, field `file`):

1. Lấy **basename** của tên file, bỏ path client gửi lên; kiểm tra đuôi thuộc whitelist
   `MP4, MOV, M4V, MKV, WEBM, AVI, MPEG, MPG, WMV, FLV`. Không dựa vào `Content-Type`.
2. Từ chối file rỗng hoặc vượt 2 GB. Kích thước khai báo được kiểm tra trước; khi ghi xuống đĩa vẫn
   đọc theo chunk 1 MiB và đếm lại, nên không thể vượt giới hạn bằng header giả.
3. Tạo thư mục mới từ `DATA_DIR/videos/{uuid}`. Tên file gốc **không bao giờ** được dùng làm
   đường dẫn.
4. Ghi file tạm `upload{ext}`. Nếu là MP4 thì chuyển thành `original.mp4`; container khác được
   remux `-c copy -movflags +faststart` (map video đầu + audio nếu có). Remux lỗi → transcode
   `libx264 -crf 20 -pix_fmt yuv420p` + AAC 192 kbps, timeout 30 phút.
5. `ffprobe` lấy thời lượng/kích thước; từ chối video không có stream video hoặc thời lượng ≤ 0.
6. Tạo `thumb.jpg` (lỗi thumbnail không làm fail upload), ghi `meta.json` gồm `source: "upload"`,
   tên gốc, kích thước, thời lượng và thời điểm upload.
7. Tạo `Video(status="ready", platform="upload", source_url="")` trong DB và trả `201` + `VideoRead`.

Mọi lỗi validation/ffmpeg đều xoá thư mục vừa tạo; không để lại record hay file rác. Helper xoá
kiểm tra thư mục là con trực tiếp của `DATA_DIR/videos` trước khi `rmtree`.

## Frontend

- `api.uploadVideo(file)` gửi `FormData`; `request()` tự bỏ JSON `Content-Type` cho FormData.
- Ô upload có 3 trạng thái: chưa chọn file, đã chọn (tên + dung lượng + nút Đổi/Bỏ), đang upload
  (spinner + disable nút). Hỗ trợ chọn file và kéo thả.
- Kiểm tra 2 GB phía client để báo sớm; backend vẫn kiểm tra lại.
- Upload xong: xoá file đã chọn, hiện thông báo **Đã thêm “…” vào thư viện**, refresh danh sách.
- `PLATFORM_LABELS/STYLES` thêm `upload`; `UploadIcon` mới.
- VideoDetail: nếu `source_url` rỗng thì hiện nhãn **Video tải lên từ máy** thay vì link `href=""`
  và cột Nguồn ghi **Tải lên từ máy**.

## File mới / thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/services/uploads.py` | **Mới** — whitelist, sanitize tên, ghi chunk có giới hạn, remux/transcode, cleanup an toàn |
| `backend/app/routers/videos.py` | **Mới** endpoint `POST /api/upload`, tạo Video + thumbnail + meta |
| `backend/tests/test_upload.py` | **Mới** — 8 test với ffmpeg thật |
| `frontend/src/api.ts` | `uploadVideo(file)` |
| `frontend/src/pages/Home.tsx` | Ô chọn/kéo thả file, trạng thái upload, refresh thư viện |
| `frontend/src/pages/VideoDetail.tsx` | Hiển thị nguồn upload thay cho link rỗng |
| `frontend/src/components/Icons.tsx` | `UploadIcon` |
| `frontend/src/lib/format.ts` | Nhãn/màu nền tảng `upload` |
| `README.md`, `implemented/README.md`, `implemented/phase-8.md` | Tài liệu |

## Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `pytest -o addopts="" -q` | **350 passed** trong 14.35s |
| `ruff check app tests` | All checks passed |
| `npm run build` | OK — CSS 48.19 kB, JS 338.51 kB (gzip 8.91 / 101.32 kB) |
| Upload MP4 thật | 201, video `ready`, `original.mp4` + `thumb.jpg` + `meta.json`, thời lượng/kích thước đúng |
| Container khác | MKV H.264/AAC remux thành MP4; MKV FFV1/PCM fallback transcode thành MP4 |
| Lỗi | Thiếu đuôi, file rác, quá dung lượng đều bị từ chối và dọn thư mục |
| Bảo mật | Filename `../../evil.mp4` chỉ còn `evil.mp4`, không ghi ra ngoài thư mục video |
| Không ghi đè | Upload cùng file hai lần tạo hai video/thư mục riêng |

**Chưa kiểm chứng end-to-end:**

- Kéo/thả và chọn file trên trình duyệt thật (repo không có frontend test harness).
- File sát 2 GB và thời gian transcode video dài/4K.
- Codec lạ ngoài các mẫu ffmpeg trong test.

## Quyết định đã chốt

- **Upload đồng bộ, không tạo job:** phù hợp app local một người dùng; endpoint sync của FastAPI
  chạy trong threadpool nên server vẫn phản hồi. Đổi lại, request giữ mở trong lúc transcode và UI
  chỉ có spinner, chưa có % tiến độ. Nếu sau này cần progress/retry thì chuyển sang job worker.
- **`source_url = ""`** thay vì URL giả: không làm bẩn dữ liệu nguồn và không ảnh hưởng logic
  chống trùng link; UI đã xử lý trường hợp rỗng.
- **Giới hạn 2 GB cố định:** đủ cho video ngắn/reup và tránh treo máy; có thể đưa vào Settings sau.
- **Whitelist đuôi + ffprobe**, không tin `Content-Type` hay magic bytes đơn lẻ: ffprobe xác nhận
  có stream video thật; đuôi giúp chặn sớm file không phải video.
- **Remux trước, transcode sau:** giữ chất lượng và tốc độ cho container phổ biến; transcode chỉ
  dùng khi MP4 không chứa được codec.
- **Thumbnail best-effort:** giống download, lỗi ảnh bìa không làm mất video đã upload.
- **Không dùng tên file làm path**, luôn tạo UUID mới: chặn traversal và bảo đảm không ghi đè
  `original.mp4` của video khác.
