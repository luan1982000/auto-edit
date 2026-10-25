import type { CoverRegion, SubtitleData, SubtitleSegment } from "../api";
import { languageLabel } from "../lib/languages";
import {
  CheckIcon,
  FilmIcon,
  RefreshIcon,
  SpinnerIcon,
  TrashIcon,
  XIcon,
} from "./Icons";

interface SubtitleEditorProps {
  data: SubtitleData | null;
  draft: SubtitleSegment[];
  targetLanguage: string;
  coverRegion: CoverRegion | null;
  loading: boolean;
  busy: boolean;
  saving: boolean;
  dirty: boolean;
  error: string;
  disabled: boolean;
  onChange: (index: number, patch: Partial<SubtitleSegment>) => void;
  onAdd: () => void;
  onDelete: (index: number) => void;
  onSave: () => void;
  onOpenTranscribe: (translate: boolean) => void;
  onOpenTranslate: () => void;
  onOpenRegion: () => void;
}

const INPUT_CLASS =
  "w-full rounded-lg border border-line bg-ink/60 px-2 py-1.5 text-[12px] text-zinc-200 outline-none transition focus:border-acid/50 disabled:opacity-45";

export function SubtitleEditor({
  data,
  draft,
  targetLanguage,
  coverRegion,
  loading,
  busy,
  saving,
  dirty,
  error,
  disabled,
  onChange,
  onAdd,
  onDelete,
  onSave,
  onOpenTranscribe,
  onOpenTranslate,
  onOpenRegion,
}: SubtitleEditorProps) {
  const locked = disabled || busy || saving;

  return (
    <section className="rounded-2xl border border-line bg-panel/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">
            Phụ đề
          </p>
          {data ? (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="rounded-md bg-ink/60 px-1.5 py-0.5 font-mono text-[10px] uppercase text-zinc-400 ring-1 ring-inset ring-line">
                {data.language || "?"}
              </span>
              <span className="text-[10px] text-zinc-700">→</span>
              <span className="rounded-md bg-ink/60 px-1.5 py-0.5 font-mono text-[10px] uppercase text-zinc-400 ring-1 ring-inset ring-line">
                {data.target_language || "?"}
              </span>
              <span
                className={`ml-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9.5px] font-medium ${
                  data.translated
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-zinc-500/10 text-zinc-400"
                }`}
              >
                {data.translated ? (
                  <CheckIcon className="size-2.5" />
                ) : (
                  <XIcon className="size-2.5" />
                )}
                {data.translated ? "Đã dịch" : "Bản gốc"}
              </span>
              <span
                className={`ml-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9.5px] font-medium ${
                  coverRegion
                    ? "bg-acid/10 text-acid"
                    : "bg-zinc-500/10 text-zinc-500"
                }`}
              >
                <FilmIcon className="size-2.5" />
                {coverRegion ? "Đang che phụ đề cũ" : "Chưa che phụ đề cũ"}
              </span>
            </div>
          ) : (
            <p className="mt-1 text-[12px] text-zinc-500">
              {loading
                ? "Đang tải phụ đề..."
                : "Nhận dạng lời nói bằng Whisper rồi dịch bằng DeepSeek."}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!data ? (
            <>
              <button
                type="button"
                onClick={() => onOpenTranscribe(false)}
                disabled={locked}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface/70 px-3 py-1.5 text-[11.5px] font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? (
                  <SpinnerIcon className="size-3.5 animate-spin" />
                ) : null}
                Tạo phụ đề
              </button>
              <button
                type="button"
                onClick={() => onOpenTranscribe(true)}
                disabled={locked}
                className="inline-flex items-center gap-1.5 rounded-lg bg-acid px-3 py-1.5 text-[11.5px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? (
                  <SpinnerIcon className="size-3.5 animate-spin" />
                ) : null}
                Tạo + dịch
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => onOpenTranscribe(false)}
                disabled={locked}
                title="Nhận dạng lại lời nói và thay toàn bộ phụ đề hiện tại"
                className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface/70 px-3 py-1.5 text-[11.5px] font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <RefreshIcon className="size-3.5" />
                Tạo lại phụ đề
              </button>
              <button
                type="button"
                onClick={onOpenTranslate}
                disabled={locked || dirty}
                title={
                  dirty ? "Lưu thay đổi trước khi dịch lại" : undefined
                }
                className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface/70 px-3 py-1.5 text-[11.5px] font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? (
                  <SpinnerIcon className="size-3.5 animate-spin" />
                ) : null}
                Dịch sang {languageLabel(targetLanguage)}
              </button>
              <button
                type="button"
                onClick={onOpenRegion}
                disabled={locked}
                title="Chụp ảnh mẫu và chỉnh vùng che phụ đề cũ"
                className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[11.5px] text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <FilmIcon className="size-3.5" />
                Vùng che
              </button>
              <button
                type="button"
                onClick={onAdd}
                disabled={locked}
                className="rounded-lg border border-line px-2.5 py-1.5 text-[11.5px] text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                + Dòng
              </button>
              <button
                type="button"
                onClick={onSave}
                disabled={locked || !dirty}
                className="inline-flex items-center gap-1.5 rounded-lg bg-acid px-3 py-1.5 text-[11.5px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                {saving ? (
                  <SpinnerIcon className="size-3.5 animate-spin" />
                ) : (
                  <CheckIcon className="size-3.5" />
                )}
                {saving ? "Đang lưu..." : "Lưu"}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rose-300">
          {error}
        </p>
      )}

      {data && (
        <>
          {draft.length > 0 ? (
            <div className="mt-4 space-y-1.5">
              <div className="grid grid-cols-[64px_64px_minmax(0,1fr)_24px] gap-2 px-1 text-[9.5px] uppercase tracking-[0.12em] text-zinc-600">
                <span>Bắt đầu</span>
                <span>Kết thúc</span>
                <span>Nội dung</span>
                <span />
              </div>
              {draft.map((segment, index) => (
                <div
                  key={index}
                  className="grid grid-cols-[64px_64px_minmax(0,1fr)_24px] items-center gap-2"
                >
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    value={segment.start}
                    disabled={locked}
                    onChange={(event) =>
                      onChange(index, { start: Number(event.target.value) })
                    }
                    className={`${INPUT_CLASS} tabular-nums`}
                    aria-label={`Bắt đầu dòng ${index + 1}`}
                  />
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    value={segment.end}
                    disabled={locked}
                    onChange={(event) =>
                      onChange(index, { end: Number(event.target.value) })
                    }
                    className={`${INPUT_CLASS} tabular-nums`}
                    aria-label={`Kết thúc dòng ${index + 1}`}
                  />
                  <input
                    type="text"
                    value={segment.text}
                    disabled={locked}
                    onChange={(event) =>
                      onChange(index, { text: event.target.value })
                    }
                    className={INPUT_CLASS}
                    aria-label={`Nội dung dòng ${index + 1}`}
                  />
                  <button
                    type="button"
                    onClick={() => onDelete(index)}
                    disabled={locked}
                    aria-label={`Xoá dòng ${index + 1}`}
                    className="grid size-6 place-items-center rounded-md text-zinc-600 transition hover:bg-rose-500/10 hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <TrashIcon className="size-3" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 rounded-xl border border-dashed border-line px-4 py-6 text-center text-[11.5px] text-zinc-600">
              Không còn dòng phụ đề. Bấm “+ Dòng” để thêm.
            </p>
          )}
          <p className="mt-3 text-[10.5px] leading-relaxed text-zinc-600">
            Mốc thời gian tính bằng giây. Lưu để cập nhật file SRT dùng khi
            render.{" "}
            {coverRegion
              ? "Khi render phụ đề, vùng che đã chọn sẽ được phủ kín trước khi vẽ phụ đề mới."
              : "Chưa chọn vùng che nên phụ đề cũ (nếu có) vẫn hiện phía sau phụ đề mới."}
          </p>
        </>
      )}
    </section>
  );
}
