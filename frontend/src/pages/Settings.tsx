import { useEffect, useState, type ReactNode } from "react";

import { api, type AppSettings } from "../api";
import { AlertIcon, CheckIcon, SpinnerIcon } from "../components/Icons";

const inputClass =
  "w-full rounded-xl border border-line bg-ink/60 px-3 py-2 text-[13px] text-zinc-100 outline-none transition focus:border-acid/50 focus:ring-2 focus:ring-acid/10";

const cookieOptions = [
  ["", "Không dùng cookies"],
  ["chrome", "Chrome"],
  ["chromium", "Chromium"],
  ["edge", "Edge"],
  ["firefox", "Firefox"],
  ["safari", "Safari"],
  ["brave", "Brave"],
  ["opera", "Opera"],
  ["vivaldi", "Vivaldi"],
] as const;

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
        {label}
      </span>
      {children}
      {hint && (
        <span className="mt-1.5 block text-[11px] leading-relaxed text-zinc-600">
          {hint}
        </span>
      )}
    </label>
  );
}

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-line bg-panel/50 p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold tracking-tight text-zinc-100">
          {title}
        </h2>
        <p className="text-[11.5px] text-zinc-600">{description}</p>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function toNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function SettingsPage() {
  const [saved, setSaved] = useState<AppSettings | null>(null);
  const [form, setForm] = useState<AppSettings | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .settings()
      .then((settings) => {
        if (alive) {
          setSaved(settings);
          setForm(settings);
        }
      })
      .catch((reason: unknown) => {
        if (alive) {
          setError(
            reason instanceof Error ? reason.message : "Không tải được cài đặt",
          );
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setForm((previous) =>
      previous ? { ...previous, [key]: value } : previous,
    );
    setStatus("idle");
  }

  async function save() {
    if (!form) return;
    setStatus("saving");
    setError("");
    try {
      const updated = await api.updateSettings(form);
      setSaved(updated);
      setForm(updated);
      setStatus("saved");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Lưu cài đặt thất bại",
      );
      setStatus("error");
    }
  }

  const dirty =
    saved !== null && form !== null && JSON.stringify(saved) !== JSON.stringify(form);

  if (!form) {
    return error ? (
      <div className="mx-auto max-w-md rounded-2xl border border-rose-500/25 bg-rose-500/[0.06] px-6 py-8 text-center">
        <AlertIcon className="mx-auto size-6 text-rose-300" />
        <p className="mt-2 text-[13px] text-rose-200">{error}</p>
      </div>
    ) : (
      <div className="grid place-items-center py-24">
        <SpinnerIcon className="size-6 animate-spin text-acid" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
            Cấu hình
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">
            Cài đặt
          </h1>
          <p className="mt-1 text-[12.5px] text-zinc-500">
            Lưu trong SQLite cục bộ — không đồng bộ đi đâu cả.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {status === "saved" && (
            <span className="inline-flex items-center gap-1.5 text-[12px] text-emerald-300">
              <CheckIcon className="size-3.5" />
              Đã lưu
            </span>
          )}
          <button
            type="button"
            onClick={() => void save()}
            disabled={!dirty || status === "saving"}
            className="rounded-xl bg-acid px-4 py-2 text-[12.5px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            {status === "saving" ? "Đang lưu..." : "Lưu thay đổi"}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300">
          {error}
        </p>
      )}

      <SettingsSection
        title="Tải xuống"
        description="Áp dụng cho mọi link mới"
      >
        <Field
          label="Cookies trình duyệt"
          hint="Cần cho Douyin hoặc video Facebook yêu cầu đăng nhập. yt-dlp sẽ đọc cookies từ trình duyệt đang chọn."
        >
          <select
            className={inputClass}
            value={form.cookies_browser}
            onChange={(event) => update("cookies_browser", event.target.value)}
          >
            {cookieOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Phụ đề"
        description="Whisper chạy local trên máy"
      >
        <Field
          label="Model Whisper"
          hint="small cân bằng tốc độ/chất lượng; medium chậm hơn nhưng chính xác hơn."
        >
          <select
            className={inputClass}
            value={form.whisper_model}
            onChange={(event) => update("whisper_model", event.target.value)}
          >
            {["tiny", "base", "small", "medium", "large-v3"].map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ngôn ngữ đích" hint="Ví dụ: vi, en, zh">
          <input
            className={inputClass}
            value={form.target_language}
            onChange={(event) => update("target_language", event.target.value)}
          />
        </Field>
        <Field label="Vị trí phụ đề">
          <select
            className={inputClass}
            value={form.subtitle_position}
            onChange={(event) =>
              update(
                "subtitle_position",
                event.target.value as AppSettings["subtitle_position"],
              )
            }
          >
            <option value="bottom">Dưới</option>
            <option value="center">Giữa</option>
            <option value="top">Trên</option>
          </select>
        </Field>
        <Field label="Cỡ chữ" hint="Đơn vị tương đối khi burn phụ đề">
          <input
            type="number"
            min={8}
            max={200}
            className={inputClass}
            value={form.subtitle_size}
            onChange={(event) =>
              update("subtitle_size", toNumber(event.target.value))
            }
          />
        </Field>
        <Field label="Font" hint="Để trống dùng font mặc định hỗ trợ tiếng Việt">
          <input
            className={inputClass}
            value={form.subtitle_font}
            placeholder="Arial"
            onChange={(event) => update("subtitle_font", event.target.value)}
          />
        </Field>
      </SettingsSection>

      <SettingsSection title="Giọng đọc" description="edge-tts, miễn phí">
        <Field label="Giọng">
          <select
            className={inputClass}
            value={form.tts_voice}
            onChange={(event) => update("tts_voice", event.target.value)}
          >
            <option value="vi-VN-HoaiMyNeural">HoaiMy (nữ)</option>
            <option value="vi-VN-NamMinhNeural">NamMinh (nam)</option>
          </select>
        </Field>
        <Field label="Tốc độ" hint="Ví dụ: +0%, +10%, -10%">
          <input
            className={inputClass}
            value={form.tts_rate}
            onChange={(event) => update("tts_rate", event.target.value)}
          />
        </Field>
      </SettingsSection>

      <SettingsSection title="Logo" description="Góc, kích thước, độ mờ">
        <Field label="Vị trí">
          <select
            className={inputClass}
            value={form.logo_position}
            onChange={(event) =>
              update(
                "logo_position",
                event.target.value as AppSettings["logo_position"],
              )
            }
          >
            <option value="tl">Trên trái</option>
            <option value="tr">Trên phải</option>
            <option value="bl">Dưới trái</option>
            <option value="br">Dưới phải</option>
          </select>
        </Field>
        <Field label="Kích thước (% chiều rộng)">
          <input
            type="number"
            min={1}
            max={100}
            className={inputClass}
            value={form.logo_scale_pct}
            onChange={(event) =>
              update("logo_scale_pct", toNumber(event.target.value))
            }
          />
        </Field>
        <Field label="Độ mờ" hint="0 = trong suốt, 1 = rõ hoàn toàn">
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            className={inputClass}
            value={form.logo_opacity}
            onChange={(event) =>
              update("logo_opacity", toNumber(event.target.value))
            }
          />
        </Field>
        <Field label="Khoảng cách viền (px)">
          <input
            type="number"
            min={0}
            max={500}
            className={inputClass}
            value={form.logo_margin_px}
            onChange={(event) =>
              update("logo_margin_px", toNumber(event.target.value))
            }
          />
        </Field>
      </SettingsSection>

      <div className="rounded-2xl border border-line/70 bg-surface/40 p-5 text-[12px] leading-relaxed text-zinc-500">
        <span className="font-medium text-zinc-300">Ghi chú:</span> Phase 1 chỉ
        dùng phần tải xuống. Các cấu hình phụ đề, giọng đọc và logo đã được lưu
        sẵn và sẽ có hiệu lực khi các phase tương ứng được bật.
      </div>
    </div>
  );
}
