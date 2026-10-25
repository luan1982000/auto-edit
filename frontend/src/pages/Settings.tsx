import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  api,
  type AppSettings,
  type Health,
  type UpdateYtdlpResponse,
} from "../api";
import {
  AlertIcon,
  CheckIcon,
  RefreshIcon,
  SpinnerIcon,
  TrashIcon,
} from "../components/Icons";
import { TTS_VOICES } from "../lib/voices";

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
  const [health, setHealth] = useState<Health | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updateResult, setUpdateResult] =
    useState<UpdateYtdlpResponse | null>(null);
  const [updateError, setUpdateError] = useState("");
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoError, setLogoError] = useState("");
  const [logoVersion, setLogoVersion] = useState(0);
  const logoInput = useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((value) => {
        if (alive) setHealth(value);
      })
      .catch(() => {
        // The update button surfaces its own errors.
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
      const patch: Partial<AppSettings> = { ...form };
      delete patch.logo_path;
      const updated = await api.updateSettings(patch);
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

  async function updateYtdlp() {
    setUpdating(true);
    setUpdateError("");
    setUpdateResult(null);
    try {
      setUpdateResult(await api.updateYtdlp());
    } catch (reason) {
      setUpdateError(
        reason instanceof Error ? reason.message : "Cập nhật yt-dlp thất bại",
      );
    } finally {
      setUpdating(false);
    }
  }

  async function uploadLogo(file: File) {
    setLogoBusy(true);
    setLogoError("");
    try {
      const updated = await api.uploadLogo(file);
      setSaved(updated);
      setForm(updated);
      setLogoVersion(Date.now());
      setStatus("idle");
    } catch (reason) {
      setLogoError(
        reason instanceof Error ? reason.message : "Upload logo thất bại",
      );
    } finally {
      setLogoBusy(false);
    }
  }

  async function removeLogo() {
    setLogoBusy(true);
    setLogoError("");
    try {
      const updated = await api.deleteLogo();
      setSaved(updated);
      setForm(updated);
      setLogoVersion(Date.now());
      setStatus("idle");
    } catch (reason) {
      setLogoError(
        reason instanceof Error ? reason.message : "Xoá logo thất bại",
      );
    } finally {
      setLogoBusy(false);
    }
  }

  const dirty =
    saved !== null && form !== null && JSON.stringify(saved) !== JSON.stringify(form);

  const logoCorner =
    form?.logo_position === "tl"
      ? { top: form.logo_margin_px, left: form.logo_margin_px }
      : form?.logo_position === "tr"
        ? { top: form.logo_margin_px, right: form.logo_margin_px }
        : form?.logo_position === "bl"
          ? { bottom: form.logo_margin_px, left: form.logo_margin_px }
          : { bottom: form?.logo_margin_px ?? 0, right: form?.logo_margin_px ?? 0 };

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

        <div className="rounded-xl border border-line/70 bg-ink/30 p-4 sm:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[12.5px] font-medium text-zinc-300">yt-dlp</p>
              <p className="mt-0.5 text-[11.5px] text-zinc-600">
                {health?.yt_dlp_version
                  ? `Phiên bản ${health.yt_dlp_version}`
                  : "Chưa đọc được phiên bản"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void updateYtdlp()}
              disabled={updating}
              className="inline-flex items-center gap-2 rounded-xl border border-line bg-panel px-3.5 py-2 text-[12px] font-medium text-zinc-200 transition hover:border-acid/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {updating ? (
                <SpinnerIcon className="size-3.5 animate-spin text-acid" />
              ) : (
                <RefreshIcon className="size-3.5" />
              )}
              {updating ? "Đang cập nhật..." : "Cập nhật yt-dlp"}
            </button>
          </div>

          {updateResult && (
            <div
              className={`mt-3 rounded-lg border px-3 py-2 text-[11.5px] leading-relaxed ${
                updateResult.ok
                  ? "border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-200"
                  : "border-rose-500/20 bg-rose-500/[0.06] text-rose-200"
              }`}
            >
              <p className="inline-flex items-center gap-1.5 font-medium">
                {updateResult.ok ? (
                  <CheckIcon className="size-3.5" />
                ) : (
                  <AlertIcon className="size-3.5" />
                )}
                {updateResult.ok
                  ? `Đã cài yt-dlp${updateResult.version ? ` ${updateResult.version}` : ""}`
                  : "Cập nhật thất bại"}
              </p>
              {updateResult.ok && updateResult.restart_required && (
                <p className="mt-1 text-emerald-200/70">
                  Khởi động lại backend để dùng bản mới.
                </p>
              )}
              {updateResult.output && (
                <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-md bg-ink/40 p-2 font-mono text-[10.5px] leading-relaxed text-zinc-400">
                  {updateResult.output}
                </pre>
              )}
            </div>
          )}

          {updateError && (
            <p className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/[0.06] px-3 py-2 text-[11.5px] text-rose-200">
              {updateError}
            </p>
          )}
        </div>
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
            {TTS_VOICES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
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
        <div className="rounded-xl border border-line/70 bg-ink/30 p-4 sm:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[12.5px] font-medium text-zinc-300">Xem trước</p>
            <p className="text-[11px] text-zinc-600">
              Mô phỏng vị trí trên khung hình 16:9
            </p>
          </div>
          <div className="relative mt-3 aspect-video overflow-hidden rounded-xl border border-line/60 bg-[radial-gradient(circle_at_30%_20%,rgba(215,254,79,0.16),transparent_55%),linear-gradient(135deg,#1c2024,#0c0f11)]">
            <div
              aria-hidden
              className="absolute inset-x-6 bottom-6 h-px bg-white/10"
            />
            {form.logo_path ? (
              <img
                key={logoVersion}
                src={api.logoUrl(logoVersion)}
                alt="Logo xem trước"
                style={{
                  ...logoCorner,
                  width: `${form.logo_scale_pct}%`,
                  opacity: form.logo_opacity,
                }}
                className="absolute max-h-[70%] object-contain"
              />
            ) : (
              <p className="absolute inset-0 grid place-items-center text-[12px] text-zinc-600">
                Chưa có logo — upload để xem trước
              </p>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              ref={logoInput}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void uploadLogo(file);
              }}
            />
            <button
              type="button"
              onClick={() => logoInput.current?.click()}
              disabled={logoBusy}
              className="inline-flex items-center gap-2 rounded-xl border border-line bg-panel px-3.5 py-2 text-[12px] font-medium text-zinc-200 transition hover:border-acid/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {logoBusy ? (
                <SpinnerIcon className="size-3.5 animate-spin text-acid" />
              ) : null}
              {logoBusy ? "Đang xử lý..." : form.logo_path ? "Đổi logo" : "Upload logo"}
            </button>
            {form.logo_path && (
              <button
                type="button"
                onClick={() => void removeLogo()}
                disabled={logoBusy}
                className="inline-flex items-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.06] px-3.5 py-2 text-[12px] font-medium text-rose-300 transition hover:border-rose-500/40 disabled:opacity-50"
              >
                <TrashIcon className="size-3.5" />
                Xoá logo
              </button>
            )}
            <span className="text-[11px] text-zinc-600">
              PNG/JPEG/WEBP, tối đa 5 MB. PNG nền trong suốt được khuyến nghị.
            </span>
          </div>
          {logoError && (
            <p className="mt-2 rounded-lg border border-rose-500/20 bg-rose-500/[0.06] px-3 py-2 text-[11.5px] text-rose-200">
              {logoError}
            </p>
          )}
        </div>

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
        <span className="font-medium text-zinc-300">Ghi chú:</span> Logo được
        lưu trong <code className="text-zinc-400">data/assets/</code>. Video gốc
        không bao giờ bị ghi đè; mỗi lần render tạo một bản{" "}
        <code className="text-zinc-400">output_final.mp4</code> riêng.
      </div>
    </div>
  );
}
