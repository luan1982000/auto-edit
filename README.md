# Reup Studio

Web app chạy **local** để tải video (Facebook Reel, Douyin, TikTok, YouTube Shorts...) về máy, tạo
phụ đề và giọng đọc, chèn logo rồi render ra một file hoàn chỉnh. Không đăng nhập, không cloud,
không multi-user.

> **Trạng thái: Phase 6/6** — tải video, phụ đề (Whisper + DeepSeek), TTS, logo, render gộp một
> lệnh ffmpeg, preset và đầy đủ UI. Xem [implemented/](implemented/) để đối chiếu từng phase.

## Yêu cầu

- Python **3.11+**
- Node.js **20+** và npm
- `ffmpeg` + `ffprobe` trong `PATH` (`brew install ffmpeg` trên macOS)
- `yt-dlp` được cài như **Python library** qua `pip` (không cần binary riêng)
- Internet khi dùng **edge-tts** (Microsoft Edge speech) và **DeepSeek**; Whisper chạy local (lần
  đầu cần mạng để tải model)

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

## Cách dùng

1. Dán một hoặc nhiều link vào ô **Danh sách link**, mỗi dòng một link. Chỉ nhận `http/https`.
   Bấm **Tải video** — mỗi link tạo một job `download` chạy trong worker thread.
2. Video tải xong xuất hiện trong **Thư viện**. Click để mở trang chi tiết và phát video (hỗ trợ
   tua — HTTP Range).
3. **Tạo phụ đề**: bấm **Nhận dạng** (Whisper, tuỳ chọn dịch luôn), hoặc **Dịch lại** nếu đã có phụ
   đề. Sửa trực tiếp trong bảng, thêm/xoá dòng, rồi **Lưu phụ đề**.
4. **Tạo giọng đọc**: chọn giọng và tốc độ, nghe thử một câu, bấm **Tạo giọng đọc**. Giọng được
   sinh cho từng segment và ghép đúng timeline phụ đề.
5. **Render**: chọn Logo / Phụ đề / Giọng đọc, chọn chế độ âm thanh gốc (`duck` / `keep` /
   `mute`), rồi **Render bản final**. Preset trong Cài đặt quyết định các checkbox mặc định khi mở
   trang video.
6. Chuyển tab **Original / Output** để so sánh, tải output hoặc mở thư mục. Bản gốc `original.mp4`
   luôn được giữ nguyên.

### Preset render

Cài đặt → **Preset render**:

| Preset | Checkbox mặc định khi mở video |
|---|---|
| `Logo` | Logo (nếu đã upload) |
| `Logo + phụ đề` | Logo + phụ đề (nếu video đã có phụ đề) |
| `Full` | Logo + phụ đề + giọng đọc (nếu video đã có voice) |

Preset chỉ là giá trị khởi tạo. Sau khi bạn tự đổi checkbox, lựa chọn của bạn được giữ cho phiên
trang đó. Khi vừa tạo giọng đọc xong, app tự bật giọng đọc + `duck` để render nhanh (với preset
`Full`; preset `Logo`/`Logo + phụ đề` sẽ tắt lại giọng đọc nếu trang chưa bị chỉnh tay).

Dữ liệu nằm trong `data/` (đã gitignore):

```
data/
  app.db
  assets/logo.png           # logo đã upload (png/jpg/webp)
  videos/{id}/
    original.mp4            # KHÔNG BAO GIỜ bị ghi đè
    thumb.jpg
    meta.json
    subtitle.json           # nguồn + bản dịch
    subtitle.srt
    subtitle.ass            # sinh khi render phụ đề
    voice.mp3
    output_final.mp4
```

`audio.wav` chỉ là file tạm khi transcribe và được xoá ngay sau đó (kể cả khi job lỗi).

## Cấu hình

`.env` (xem `.env.example`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATA_DIR` | `./data` | Nơi lưu DB, video, asset |
| `DEEPSEEK_API_KEY` | rỗng | Dịch phụ đề bằng DeepSeek; thiếu key chỉ tắt tính năng dịch |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Base URL API DeepSeek (OpenAI-compatible) |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model dùng để dịch |
| `DOUYIN_FALLBACK_URL` | rỗng | HTTP fallback cho Douyin, tắt khi rỗng (xem bên dưới) |
| `JOB_TIMEOUT_SEC` | `900` | Giới hạn thời gian 1 job |
| `BIND_HOST` | `127.0.0.1` | Địa chỉ bind khi chạy uvicorn trực tiếp |
| `BIND_PORT` | `8000` | Cổng backend |

Settings trong UI (lưu ở bảng `settings`): cookies trình duyệt, model Whisper, ngôn ngữ đích,
font/cỡ/vị trí phụ đề, giọng TTS, tốc độ đọc, preset render, góc/kích thước/độ mờ/margin logo.

### Cookies

Chọn trình duyệt ở **Cài đặt → Cookies trình duyệt** để yt-dlp đọc cookies
(`cookiesfrombrowser`). Cần cho Douyin hoặc video Facebook yêu cầu đăng nhập. Đóng trình duyệt
nếu yt-dlp báo không đọc được cookie (một số bản Chrome khoá file cookie khi đang chạy).

### DeepSeek (dịch phụ đề)

Điền `DEEPSEEK_API_KEY` vào `.env` rồi khởi động lại backend. App gửi **một request** chứa toàn bộ
segment, yêu cầu DeepSeek trả JSON giữ nguyên id/thứ tự. Response được kiểm tra chặt: đủ id, không
trùng, không rỗng; sai format → job `failed` với lỗi rõ. Nếu ngôn ngữ nguồn trùng ngôn ngữ đích,
app bỏ qua bước dịch. Thiếu key: job dịch báo `Chưa cấu hình DEEPSEEK_API_KEY...`, các tính năng
khác vẫn chạy bình thường.

### Logo

Vào **Cài đặt → Logo**: upload PNG/JPEG/WEBP tối đa **5 MB** (ưu tiên PNG nền trong suốt). App
nhận diện file bằng magic bytes, lưu vào `DATA_DIR/assets/` và chỉ phục vụ file nằm trong thư mục
này. Panel xem trước mô phỏng vị trí/góc/kích thước/độ mờ trên khung 16:9. Logo thật được scale
theo **% chiều rộng video**, giữ tỉ lệ, áp opacity và margin khi render.

### Phụ đề

- **Whisper local** (`faster-whisper`), model chọn trong Cài đặt (`tiny` / `base` / `small` /
  `medium`...). Model được cache trong tiến trình; lần đầu dùng một model sẽ tải về.
- Audio được tách thành WAV 16 kHz mono, nhận dạng có VAD; progress cập nhật theo timestamp.
- Phụ đề lưu `subtitle.json` (giữ cả bản nguồn để **Dịch lại**) và `subtitle.srt`.
- Khi burn, app sinh `subtitle.ass` theo kích thước video, font/cỡ/vị trí trong Cài đặt; tự xuống
  dòng (~40 ký tự/dòng cho video dọc, ~60 cho video ngang), có viền + bóng và hỗ trợ tiếng Việt có
  dấu. Tên font phải là font hệ thống ffmpeg/libass tìm thấy (mặc định `Arial`).

### Giọng đọc (TTS)

- Engine mặc định **edge-tts**, hai giọng có sẵn: `vi-VN-HoaiMyNeural` (nữ) và
  `vi-VN-NamMinhNeural` (nam), tốc độ `-20%` … `+20%`.
- **Nghe thử** đọc câu phụ đề đầu tiên chưa lưu (tối đa 1000 ký tự). **Tạo giọng đọc** sinh MP3
  cho từng segment, tăng tốc tối đa **1.4x** nếu audio dài hơn khung thời gian, rồi đặt từng clip
  đúng mốc bằng `adelay`, trộn bằng `amix`, đệm im lặng đến hết video và giới hạn biên độ.
- Sửa phụ đề chưa lưu sẽ chặn tạo voice để tránh lệch timeline; lưu hoặc tải lại trước.
- Voice và tốc độ được chụp vào job lúc bấm tạo, nên đổi Cài đặt giữa chừng không ảnh hưởng job
  đang chạy.

### Render

Toàn bộ logo + phụ đề + voice được gộp vào **một lệnh ffmpeg duy nhất** (encode video một lần):

- Video: `libx264 -crf 20 -preset medium`, `yuv420p`, `+faststart`.
- Voice: AAC 192 kbps. Không có voice: giữ audio gốc bằng `-c:a copy`.
- Ba chế độ audio gốc khi có voice:
  - `duck` — giảm âm gốc còn 20%, mix với voice (mặc định);
  - `keep` — giữ nguyên âm gốc, mix với voice;
  - `mute` — chỉ voice.
- Nếu video gốc không có audio, `mute` và `duck` đều cho ra voice-only thay vì lỗi.
- Output ghi vào `output_final.tmp.mp4` rồi mới đổi tên thành `output_final.mp4`; lỗi giữa chừng
  không làm hỏng bản output cũ và không bao giờ chạm vào `original.mp4`.
- Progress lấy từ `ffmpeg -progress pipe:1` (%, thật), có timeout và deadline của job.

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
| GET | `/api/videos/{id}` | Chi tiết + `has_subtitle` / `has_voice` / `has_output` |
| DELETE | `/api/videos/{id}` | Xoá record + thư mục + job liên quan |
| GET | `/api/videos/{id}/file?variant=original\|output` | Stream, hỗ trợ Range |
| GET | `/api/videos/{id}/thumb` | JPEG |
| POST | `/api/videos/{id}/open-folder` | Mở Finder/Explorer |
| POST | `/api/videos/{id}/transcribe` | `{translate?: bool}` → job transcribe (+ dịch) |
| POST | `/api/videos/{id}/translate` | `{target_language?}` → job dịch lại từ bản nguồn |
| GET/PUT | `/api/videos/{id}/subtitle` | Đọc/lưu `{segments: [{start,end,text}]}` |
| POST | `/api/videos/{id}/tts` | `{voice?, rate?}` → job tạo `voice.mp3` |
| POST | `/api/tts/preview` | `{text, voice?, rate?}` → MP3 nghe thử |
| POST | `/api/videos/{id}/render` | `{logo, subtitle, voice, keep_original_audio}` → job render |
| GET | `/api/jobs` | `?status=pending\|running\|done\|failed`, `?video_id=` |
| GET | `/api/jobs/{id}` | Trạng thái + tiến độ + lỗi |
| GET/PUT | `/api/settings` | Đọc/ghi settings (gồm `render_preset`) |
| POST/GET/DELETE | `/api/settings/logo` | Upload / xem / xoá logo |
| GET | `/api/health` | Trạng thái ffmpeg/ffprobe/yt-dlp |
| POST | `/api/system/update-ytdlp` | `pip install --upgrade yt-dlp`, trả output + version |

## Quyết định triển khai (ghi chú)

- **Repo root là project root** (không có thư mục con `video-tool/` như cây thư mục minh hoạ trong
  PLAN).
- Dùng **SQLModel** (được PLAN cho phép) để giảm boilerplate.
- **Không kill app khi thiếu tool**: log lỗi + `/api/health` + badge UI; tránh việc server chết
  trước khi người dùng kịp đọc lỗi.
- **Timeout job** được enforce hợp tác qua progress hook (`ctx.check_deadline`) và
  `socket_timeout=30` của yt-dlp. Download chạy in-process nên không thể kill cứng như subprocess;
  render/TTS có thêm timeout riêng cho ffmpeg/edge-tts.
- **Thumbnail lỗi không làm fail job**: video vẫn `ready`, chỉ thiếu ảnh bìa.
- **Re-download luôn tạo id/thư mục mới** (`force=true`), bảo đảm không ghi đè `original.mp4`.
- **Chuẩn hoá Douyin**: chỉ chấp nhận redirect về host `douyin.com`/`iesdouyin.com`; nếu resolve
  lỗi hoặc redirect ra ngoài, app dùng URL gốc để yt-dlp vẫn thử được.
- **Retry** áp dụng cho mọi `DownloadError` của yt-dlp (kể cả login/unsupported) để đơn giản;
  job timeout không bị retry.
- **Fallback Douyin** chỉ chạy khi được cấu hình, trả file MP4 và không ghi đè `original.mp4`.
- **Update yt-dlp** chạy bằng `sys.executable -m pip ...` với list args cố định, không nhận input
  từ client; cần restart backend để nạp module mới.
- **Dịch phụ đề dùng DeepSeek API** (`DEEPSEEK_API_KEY`) thay cho Claude, theo yêu cầu; key đọc từ
  `.env`, thiếu key chỉ tắt tính năng dịch.
- **Logo** được scale trực tiếp theo chiều rộng video (đã biết từ ffprobe) thay vì `scale2ref`;
  cùng kết quả, ít phụ thuộc filter graph hơn, và đảm bảo chiều rộng chẵn cho `yuv420p`.
- **ASS thay vì SRT burn**: kiểm soát font, cỡ, viền, vị trí và xuống dòng; file ASS nằm trong thư
  mục video và ffmpeg chạy với `cwd` là thư mục đó nên tên file luôn được validate.
- **Render một pass**: mọi filter video/audio nằm trong một `-filter_complex`, output tạm rồi
  `replace`; progress parse từ `-progress pipe:1`.
- **Preset render** lưu ở cột `render_preset`; DB cũ được migrate idempotent bằng `ALTER TABLE`.
- **TTS**: mỗi segment một file tạm; audio dài hơn khung được tăng tốc tối đa 1.4x, quá nữa thì tràn
  nhẹ sang khoảng trống kế tiếp (đúng PLAN). Voice luôn được `apad` + cắt theo thời lượng video.
- **Ducking** dùng `volume=0.2` trên âm gốc (đơn giản, ổn định) thay vì sidechaincompress.
- Path video luôn dựng từ `DATA_DIR + id`; endpoint file/thumbnail kiểm tra path nằm trong thư mục
  video. Mọi lệnh ffmpeg/yt-dlp/edge-tts dùng list args, không `shell=True`; voice/rate và tên file
  subtitle được validate bằng regex.

## Troubleshooting

| Triệu chứng | Cách xử lý |
|---|---|
| `ffmpeg not found` / badge “Thiếu công cụ” | Cài ffmpeg và mở lại app |
| Facebook/Douyin báo lỗi login / 403 | Chọn cookies trình duyệt trong Settings |
| yt-dlp lỗi “Unsupported URL” / extractor hỏng | Bấm **Cập nhật yt-dlp** trong Cài đặt (hoặc `.venv/bin/pip install -U yt-dlp`), rồi khởi động lại backend |
| Douyin vẫn lỗi | Chọn cookies trình duyệt, cập nhật yt-dlp; nếu vẫn lỗi, bật `DOUYIN_FALLBACK_URL` |
| Job dịch báo thiếu `DEEPSEEK_API_KEY` | Điền key vào `.env`, restart backend |
| DeepSeek lỗi 401/402/429 | Kiểm tra key, số dư/quota và thử lại; lỗi gốc được hiện trong job |
| Whisper chậm / hết RAM | Chọn model `tiny`/`base`; lần đầu tải model cần mạng |
| Phụ đề hiện ô vuông hoặc mất dấu | Chọn font hệ thống có hỗ trợ tiếng Việt trong Cài đặt (ví dụ `Arial`) |
| Không tạo được giọng đọc | Kiểm tra mạng (edge-tts gọi service Microsoft), thử lại; sửa/lưu phụ đề trước |
| Nghe thử báo 502 | edge-tts không kết nối được; xem chi tiết lỗi trong thông báo |
| Render báo “Chưa upload logo” | Upload logo trong Cài đặt hoặc bỏ chọn Logo |
| Render báo “Chưa có phụ đề/giọng đọc” | Tạo thành phần tương ứng trước, hoặc bỏ chọn checkbox |
| Output không có tiếng | Kiểm tra video gốc có audio; với voice, thử chế độ `keep`/`duck` và xem lại file gốc |

Video Douyin có watermark chạy ngang — ngoài scope, không xử lý.

## Các phase

- **Phase 1 (xong)**: skeleton, download, library, streaming.
- **Phase 2 (xong)**: Douyin, cookies, retry, fallback HTTP, update yt-dlp.
- **Phase 3 (xong)**: upload logo + preview + overlay ffmpeg.
- **Phase 4 (xong)**: Whisper transcribe, dịch bằng **DeepSeek API**, sửa phụ đề, burn ASS.
- **Phase 5 (xong)**: edge-tts khớp timing, mix audio `mute`/`duck`/`keep`.
- **Phase 6 (xong)**: render gộp 1 lệnh ffmpeg, progress thật, preset, tab Original/Output,
  dọn file tạm, README/tài liệu.

Chi tiết từng phase, file thay đổi và kết quả kiểm chứng nằm trong [implemented/](implemented/).

Chỉ dùng cho mục đích cá nhân; bạn tự chịu trách nhiệm khi đăng lại nội dung.
