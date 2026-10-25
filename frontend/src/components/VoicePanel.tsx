import { PlayIcon, RefreshIcon, SpinnerIcon } from "./Icons";
import { TTS_RATES, TTS_RATE_LABELS, TTS_VOICES } from "../lib/voices";

interface VoicePanelProps {
  hasSubtitle: boolean;
  hasVoice: boolean;
  dirty: boolean;
  voice: string;
  rate: string;
  previewText: string;
  previewing: boolean;
  busy: boolean;
  disabled: boolean;
  error: string;
  onVoiceChange: (voice: string) => void;
  onRateChange: (rate: string) => void;
  onPreview: () => void;
  onGenerate: () => void;
}

const SELECT_CLASS =
  "w-full rounded-xl border border-line bg-ink/60 px-3 py-2 text-[12.5px] text-zinc-200 outline-none transition focus:border-acid/50 disabled:opacity-45";

export function VoicePanel({
  hasSubtitle,
  hasVoice,
  dirty,
  voice,
  rate,
  previewText,
  previewing,
  busy,
  disabled,
  error,
  onVoiceChange,
  onRateChange,
  onPreview,
  onGenerate,
}: VoicePanelProps) {
  const locked = disabled || busy;
  const rateOptions = TTS_RATES.includes(rate as (typeof TTS_RATES)[number])
    ? [...TTS_RATES]
    : [...TTS_RATES, rate];

  return (
    <section className="rounded-2xl border border-line bg-panel/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">
            Giọng đọc
          </p>
          <p className="mt-1 text-[12px] text-zinc-500">
            edge-tts đọc từng câu phụ đề theo đúng mốc thời gian.
          </p>
        </div>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9.5px] font-medium ${
            hasVoice
              ? "bg-emerald-500/10 text-emerald-300"
              : "bg-zinc-500/10 text-zinc-400"
          }`}
        >
          {hasVoice ? "Đã có voice.mp3" : "Chưa tạo giọng"}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-zinc-600">
            Giọng
          </span>
          <select
            value={voice}
            disabled={locked}
            onChange={(event) => onVoiceChange(event.target.value)}
            className={SELECT_CLASS}
          >
            {TTS_VOICES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-zinc-600">
            Tốc độ
          </span>
          <select
            value={rate}
            disabled={locked}
            onChange={(event) => onRateChange(event.target.value)}
            className={SELECT_CLASS}
          >
            {rateOptions.map((item) => (
              <option key={item} value={item}>
                {TTS_RATE_LABELS[item] ?? item}
              </option>
            ))}
          </select>
        </label>
      </div>

      {previewText ? (
        <p className="mt-3 truncate rounded-lg border border-line/60 bg-ink/30 px-3 py-2 text-[11px] text-zinc-500">
          <span className="text-zinc-600">Nghe thử: </span>
          {previewText}
        </p>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-line px-3 py-2 text-[11px] text-zinc-600">
          {hasSubtitle
            ? "Chưa có câu phụ đề nào để nghe thử."
            : "Tạo phụ đề trước để nghe thử và tạo giọng đọc."}
        </p>
      )}

      {error && (
        <p className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rose-300">
          {error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onPreview}
          disabled={locked || !previewText || previewing}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface/70 px-3 py-1.5 text-[11.5px] font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {previewing ? (
            <SpinnerIcon className="size-3.5 animate-spin" />
          ) : (
            <PlayIcon className="size-3.5" />
          )}
          {previewing ? "Đang tạo..." : "Nghe thử"}
        </button>
        <button
          type="button"
          onClick={onGenerate}
          disabled={locked || !hasSubtitle || dirty}
          title={dirty ? "Lưu thay đổi phụ đề trước" : undefined}
          className="inline-flex items-center gap-1.5 rounded-lg bg-acid px-3 py-1.5 text-[11.5px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? (
            <SpinnerIcon className="size-3.5 animate-spin" />
          ) : (
            <RefreshIcon className="size-3.5" />
          )}
          {busy
            ? "Đang tạo giọng..."
            : hasVoice
              ? "Tạo lại giọng đọc"
              : "Tạo giọng đọc"}
        </button>
      </div>

      <p className="mt-2 text-[10.5px] leading-relaxed text-zinc-600">
        {dirty
          ? "Lưu phụ đề trước khi tạo giọng để dùng đúng nội dung mới."
          : hasVoice
            ? "Tạo lại sẽ thay thế voice.mp3 cũ sau khi hoàn tất."
            : "Audio được ghép vào voice.mp3, sẵn sàng cho bước render."}
      </p>
    </section>
  );
}
