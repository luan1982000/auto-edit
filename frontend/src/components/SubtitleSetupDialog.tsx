import { useEffect, useRef, useState } from "react";

import {
  api,
  type CoverRegion,
  type SampleFrame,
} from "../api";
import {
  AUTO_SOURCE_LANGUAGE,
  SOURCE_LANGUAGES,
  TARGET_LANGUAGES,
} from "../lib/languages";
import { FrameRegionPicker, DEFAULT_COVER_REGION } from "./FrameRegionPicker";
import { AlertIcon, SpinnerIcon, XIcon } from "./Icons";

export type SubtitleDialogMode = "transcribe" | "translate" | "region";

export interface SubtitleDialogPayload {
  mode: SubtitleDialogMode;
  translate: boolean;
  sourceLanguage: string | null;
  targetLanguage: string | null;
  region: CoverRegion | null;
}

interface SubtitleSetupDialogProps {
  mode: SubtitleDialogMode;
  videoId: string;
  initialTranslate: boolean;
  initialSourceLanguage: string | null;
  initialTargetLanguage: string;
  initialRegion: CoverRegion | null;
  submitting: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (payload: SubtitleDialogPayload) => void;
}

const SELECT_CLASS =
  "w-full rounded-xl border border-line bg-ink/60 px-3 py-2 text-[12.5px] text-zinc-100 outline-none transition focus:border-acid/50 disabled:opacity-45";

function dialogTitle(mode: SubtitleDialogMode): string {
  if (mode === "translate") return "Dịch lại phụ đề";
  if (mode === "region") return "Vùng che phụ đề cũ";
  return "Tạo phụ đề mới";
}

export function SubtitleSetupDialog({
  mode,
  videoId,
  initialTranslate,
  initialSourceLanguage,
  initialTargetLanguage,
  initialRegion,
  submitting,
  error,
  onClose,
  onSubmit,
}: SubtitleSetupDialogProps) {
  const needsFrames = mode !== "translate";
  const [frames, setFrames] = useState<SampleFrame[]>([]);
  const [region, setRegion] = useState<CoverRegion | null>(initialRegion);
  const [sourceLanguage, setSourceLanguage] = useState(
    initialSourceLanguage ?? AUTO_SOURCE_LANGUAGE,
  );
  const [translate, setTranslate] = useState(initialTranslate);
  const [targetLanguage, setTargetLanguage] = useState(initialTargetLanguage);
  const [framesState, setFramesState] = useState<"loading" | "ready" | "error">(
    needsFrames ? "loading" : "ready",
  );
  const [framesError, setFramesError] = useState("");
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) onCloseRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [submitting]);

  useEffect(() => {
    if (!needsFrames) return;
    let alive = true;
    setFramesState("loading");
    setFramesError("");
    api
      .sampleFrames(videoId)
      .then((payload) => {
        if (!alive) return;
        setFrames(payload.frames);
        setRegion(payload.region ?? DEFAULT_COVER_REGION);
        setFramesState("ready");
      })
      .catch((reason: unknown) => {
        if (!alive) return;
        setFramesState("error");
        setFramesError(
          reason instanceof Error
            ? reason.message
            : "Không chụp được ảnh mẫu từ video",
        );
      });
    return () => {
      alive = false;
    };
  }, [needsFrames, videoId]);

  function retryFrames() {
    setFramesState("loading");
    setFramesError("");
    api
      .sampleFrames(videoId)
      .then((payload) => {
        setFrames(payload.frames);
        setRegion(payload.region ?? DEFAULT_COVER_REGION);
        setFramesState("ready");
      })
      .catch((reason: unknown) => {
        setFramesState("error");
        setFramesError(
          reason instanceof Error
            ? reason.message
            : "Không chụp được ảnh mẫu từ video",
        );
      });
  }

  const blockedByFrames = needsFrames && framesState === "loading";
  const actionLabel =
    mode === "region"
      ? "Lưu vùng che"
      : mode === "translate"
        ? "Dịch phụ đề"
        : translate
          ? "Tạo + dịch"
          : "Tạo phụ đề";

  function submit() {
    if (blockedByFrames || submitting) return;
    const wantsTranslation =
      mode === "translate" || (mode === "transcribe" && translate);
    onSubmit({
      mode,
      translate: mode === "translate" ? false : translate,
      sourceLanguage:
        mode === "transcribe" ? sourceLanguage || null : null,
      targetLanguage: wantsTranslation ? targetLanguage : null,
      region: mode === "translate" ? null : region,
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-ink/85 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="subtitle-dialog-title"
        className="my-auto w-full max-w-2xl rounded-2xl border border-line bg-panel p-5 shadow-2xl shadow-black/50"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">
              Phụ đề
            </p>
            <h2
              id="subtitle-dialog-title"
              className="mt-1 text-lg font-semibold tracking-tight text-white"
            >
              {dialogTitle(mode)}
            </h2>
            <p className="mt-1 text-[11.5px] leading-relaxed text-zinc-500">
              {mode === "translate"
                ? "Chọn ngôn ngữ đích cho bản dịch DeepSeek."
                : "Xem trước vài khung hình để khoanh đúng vùng phụ đề cũ trước khi burn phụ đề mới."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Đóng"
            className="grid size-7 shrink-0 place-items-center rounded-lg text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200 disabled:opacity-40"
          >
            <XIcon className="size-4" />
          </button>
        </div>

        {needsFrames && (
          <div className="mt-4 rounded-xl border border-line/70 bg-ink/30 p-3.5">
            {framesState === "loading" && (
              <div className="flex items-center gap-2.5 py-8 text-[12px] text-zinc-500">
                <SpinnerIcon className="size-4 animate-spin text-acid" />
                Đang chụp 2–3 khung hình từ video...
              </div>
            )}
            {framesState === "error" && (
              <div className="space-y-2">
                <p className="flex items-start gap-2 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rose-300">
                  <AlertIcon className="mt-0.5 size-3.5 shrink-0" />
                  {framesError}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={retryFrames}
                    className="rounded-lg border border-line px-2.5 py-1 text-[10.5px] text-zinc-300 transition hover:border-zinc-600"
                  >
                    Thử lại
                  </button>
                  <span className="text-[10.5px] text-zinc-600">
                    Vẫn có thể tiếp tục với vùng che đã lưu.
                  </span>
                </div>
              </div>
            )}
            {framesState === "ready" && frames.length > 0 && (
              <FrameRegionPicker
                frames={frames}
                region={region}
                disabled={submitting}
                onChange={setRegion}
              />
            )}
          </div>
        )}

        {mode !== "region" && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {mode === "transcribe" && (
              <label className="block">
                <span className="mb-1.5 block text-[10.5px] font-medium uppercase tracking-[0.12em] text-zinc-500">
                  Ngôn ngữ nói trong video
                </span>
                <select
                  className={SELECT_CLASS}
                  value={sourceLanguage}
                  disabled={submitting}
                  onChange={(event) => setSourceLanguage(event.target.value)}
                >
                  <option value={AUTO_SOURCE_LANGUAGE}>
                    Tự động nhận dạng
                  </option>
                  {SOURCE_LANGUAGES.map((language) => (
                    <option key={language.value} value={language.value}>
                      {language.label} ({language.value})
                    </option>
                  ))}
                </select>
              </label>
            )}

            {mode === "transcribe" && (
              <label className="flex cursor-pointer items-center gap-2.5 self-end rounded-xl border border-line/70 bg-ink/30 px-3 py-2.5">
                <input
                  type="checkbox"
                  checked={translate}
                  disabled={submitting}
                  onChange={(event) => setTranslate(event.target.checked)}
                  className="size-3.5 accent-[var(--color-acid)]"
                />
                <span>
                  <span className="block text-[12.5px] font-medium text-zinc-200">
                    Dịch bằng DeepSeek
                  </span>
                  <span className="text-[10.5px] text-zinc-600">
                    Dịch ngay sau khi nhận dạng
                  </span>
                </span>
              </label>
            )}

            {(mode === "translate" || translate) && (
              <label className="block sm:col-span-2">
                <span className="mb-1.5 block text-[10.5px] font-medium uppercase tracking-[0.12em] text-zinc-500">
                  Ngôn ngữ đích
                </span>
                <select
                  className={SELECT_CLASS}
                  value={targetLanguage}
                  disabled={submitting}
                  onChange={(event) => setTargetLanguage(event.target.value)}
                >
                  {TARGET_LANGUAGES.map((language) => (
                    <option key={language.value} value={language.value}>
                      {language.label} ({language.value})
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        )}

        {mode !== "translate" && (
          <p className="mt-3 text-[10.5px] leading-relaxed text-zinc-600">
            Vùng che được phủ một lớp đen đặc trước khi logo và phụ đề mới
            được vẽ lên. Video gốc không bị sửa; chỉ bản render bị ảnh hưởng.
          </p>
        )}

        {error && (
          <p className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rose-300">
            {error}
          </p>
        )}

        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-lg border border-line px-3 py-1.5 text-[12px] text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-200 disabled:opacity-40"
          >
            Huỷ
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || blockedByFrames}
            className="inline-flex items-center gap-1.5 rounded-lg bg-acid px-3.5 py-1.5 text-[12px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting && <SpinnerIcon className="size-3.5 animate-spin" />}
            {submitting ? "Đang lưu..." : actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
