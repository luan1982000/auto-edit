import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  api,
  type AppSettings,
  type AudioMode,
  type Job,
  type RenderOptions,
  type SubtitleData,
  type SubtitleSegment,
  type Video,
} from "../api";
import { JobCard } from "../components/JobCard";
import { SubtitleEditor } from "../components/SubtitleEditor";
import { VoicePanel } from "../components/VoicePanel";
import {
  AlertIcon,
  ArrowLeftIcon,
  CheckIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FolderIcon,
  SpinnerIcon,
  TrashIcon,
  XIcon,
} from "../components/Icons";
import { StatusDot } from "../components/VideoCard";
import {
  formatDate,
  formatDuration,
  formatResolution,
  platformLabel,
  platformStyle,
} from "../lib/format";

function VariantButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition ${
        active
          ? "bg-acid text-ink"
          : "text-zinc-400 hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-30"
      }`}
    >
      {children}
    </button>
  );
}

function OptionToggle({
  checked,
  disabled,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label
      className={`flex items-start gap-2.5 rounded-xl border border-line/70 bg-ink/30 px-3 py-2.5 ${
        disabled ? "opacity-45" : "cursor-pointer"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-3.5 accent-[var(--color-acid)]"
      />
      <span className="min-w-0">
        <span className="block text-[12.5px] font-medium text-zinc-200">
          {label}
        </span>
        {hint && (
          <span className="mt-0.5 block text-[10.5px] leading-relaxed text-zinc-600">
            {hint}
          </span>
        )}
      </span>
    </label>
  );
}

const AUDIO_MODES: Array<{ value: AudioMode; label: string }> = [
  { value: "duck", label: "Giảm âm gốc khi có giọng đọc" },
  { value: "keep", label: "Giữ âm gốc" },
  { value: "mute", label: "Tắt âm gốc" },
];

export function VideoDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [video, setVideo] = useState<Video | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [renderError, setRenderError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [variant, setVariant] = useState<"original" | "output">("original");
  const [outputVersion, setOutputVersion] = useState(0);
  const [options, setOptions] = useState<RenderOptions>({
    logo: true,
    subtitle: false,
    voice: false,
    keep_original_audio: "keep",
  });
  const [optionsTouched, setOptionsTouched] = useState(false);
  const [startingRender, setStartingRender] = useState(false);
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [subtitle, setSubtitle] = useState<SubtitleData | null>(null);
  const [subtitleDraft, setSubtitleDraft] = useState<SubtitleSegment[]>([]);
  const [subtitleDirty, setSubtitleDirty] = useState(false);
  const [subtitleLoading, setSubtitleLoading] = useState(false);
  const [subtitleSaving, setSubtitleSaving] = useState(false);
  const [subtitleError, setSubtitleError] = useState("");
  const [ttsVoice, setTtsVoice] = useState("vi-VN-HoaiMyNeural");
  const [ttsRate, setTtsRate] = useState("+0%");
  const [previewing, setPreviewing] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const subtitleDirtyRef = useRef(false);
  const outputState = useRef({ id: "", has: false });
  const previousHasVoice = useRef<boolean | null>(null);
  const voiceTouched = useRef(false);
  const previewAudio = useRef<{ audio: HTMLAudioElement; url: string } | null>(
    null,
  );

  useEffect(() => {
    let alive = true;
    api
      .settings()
      .then((value) => {
        if (alive) setSettings(value);
      })
      .catch(() => {
        // Render still works without logo; the backend reports missing files.
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    const load = async () => {
      try {
        const [nextVideo, nextJobs] = await Promise.all([
          api.video(id),
          api.jobs(undefined, id),
        ]);
        if (alive) {
          setVideo(nextVideo);
          setJobs(nextJobs);
          setLoadError("");
        }
      } catch (error) {
        if (alive) {
          setLoadError(
            error instanceof Error ? error.message : "Không tải được video",
          );
        }
      }
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 2000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [id]);

  useEffect(() => {
    if (!settings || voiceTouched.current) return;
    setTtsVoice(settings.tts_voice);
    setTtsRate(settings.tts_rate);
  }, [settings]);

  useEffect(() => {
    if (!video) return;
    if (previousHasVoice.current === false && video.has_voice) {
      setOptionsTouched(true);
      setOptions((current) => ({
        ...current,
        voice: true,
        keep_original_audio: "duck",
      }));
    }
    previousHasVoice.current = video.has_voice;
  }, [video]);

  useEffect(() => () => stopVoicePreview(), []);

  useEffect(() => {
    if (!video || !settings || optionsTouched) return;
    const preset = settings.render_preset;
    const wantsVoice = preset === "full" && video.has_voice;
    setOptions({
      logo: Boolean(settings.logo_path),
      subtitle: preset !== "logo" && video.has_subtitle,
      voice: wantsVoice,
      keep_original_audio: wantsVoice ? "duck" : "keep",
    });
  }, [video, settings, optionsTouched]);

  useEffect(() => {
    if (!video) return;
    const previous = outputState.current;
    if (
      previous.id === video.id &&
      video.has_output &&
      !previous.has
    ) {
      setOutputVersion(Date.now());
      setVariant("output");
    }
    outputState.current = { id: video.id, has: video.has_output };
  }, [video]);

  const hasSubtitle = video?.has_subtitle ?? false;
  const latestSubtitleDone =
    jobs.find(
      (job) =>
        (job.type === "transcribe" || job.type === "translate") &&
        job.status === "done",
    )?.id ?? "";

  useEffect(() => {
    if (!id) return;
    if (!hasSubtitle) {
      setSubtitle(null);
      setSubtitleDraft([]);
      setSubtitleDirty(false);
      setSubtitleLoading(false);
      subtitleDirtyRef.current = false;
      return;
    }
    if (subtitleDirtyRef.current) return;
    let alive = true;
    setSubtitleLoading(true);
    api
      .subtitle(id)
      .then((data) => {
        if (!alive) return;
        setSubtitle(data);
        setSubtitleDraft(data.segments);
        setSubtitleError("");
      })
      .catch((error) => {
        if (alive) {
          setSubtitleError(
            error instanceof Error ? error.message : "Không tải được phụ đề",
          );
        }
      })
      .finally(() => {
        if (alive) setSubtitleLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [id, hasSubtitle, latestSubtitleDone]);

  function changeOptions(patch: Partial<RenderOptions>) {
    setOptionsTouched(true);
    setOptions((current) => ({ ...current, ...patch }));
  }

  function trackJob(job: Job) {
    setPendingJobId(job.id);
    setJobs((current) => [
      job,
      ...current.filter((item) => item.id !== job.id),
    ]);
  }

  function markSubtitleDirty() {
    subtitleDirtyRef.current = true;
    setSubtitleDirty(true);
  }

  function changeSubtitle(index: number, patch: Partial<SubtitleSegment>) {
    setSubtitleDraft((current) =>
      current.map((segment, position) =>
        position === index ? { ...segment, ...patch } : segment,
      ),
    );
    markSubtitleDirty();
    setSubtitleError("");
  }

  function addSubtitleRow() {
    setSubtitleDraft((current) => {
      const last = current[current.length - 1];
      const start = last ? Math.max(last.end, 0) : 0;
      return [
        ...current,
        {
          start: Number(start.toFixed(1)),
          end: Number((start + 2).toFixed(1)),
          text: "",
        },
      ];
    });
    markSubtitleDirty();
    setSubtitleError("");
  }

  function deleteSubtitleRow(index: number) {
    setSubtitleDraft((current) =>
      current.filter((_, position) => position !== index),
    );
    markSubtitleDirty();
    setSubtitleError("");
  }

  async function handleSaveSubtitle() {
    if (!id || !subtitle) return;
    const invalidIndex = subtitleDraft.findIndex(
      (segment) =>
        !segment.text.trim() || segment.end <= segment.start || segment.start < 0,
    );
    if (invalidIndex >= 0) {
      setSubtitleError(
        `Dòng ${invalidIndex + 1}: kiểm tra lại mốc thời gian và nội dung`,
      );
      return;
    }
    setSubtitleSaving(true);
    setSubtitleError("");
    try {
      const saved = await api.saveSubtitle(
        id,
        subtitleDraft.map((segment) => ({
          start: segment.start,
          end: segment.end,
          text: segment.text.trim(),
        })),
      );
      setSubtitle(saved);
      setSubtitleDraft(saved.segments);
      subtitleDirtyRef.current = false;
      setSubtitleDirty(false);
    } catch (error) {
      setSubtitleError(
        error instanceof Error ? error.message : "Không lưu được phụ đề",
      );
    } finally {
      setSubtitleSaving(false);
    }
  }

  async function handleTranscribe(translate: boolean) {
    if (!video) return;
    if (
      subtitleDirtyRef.current &&
      !window.confirm("Bỏ các thay đổi phụ đề chưa lưu?")
    ) {
      return;
    }
    setSubtitleError("");
    try {
      const job = await api.transcribe(video.id, translate);
      subtitleDirtyRef.current = false;
      setSubtitleDirty(false);
      trackJob(job);
    } catch (error) {
      setSubtitleError(
        error instanceof Error ? error.message : "Không bắt đầu được job",
      );
    }
  }

  async function handleTranslate() {
    if (!video) return;
    if (subtitleDirtyRef.current) {
      setSubtitleError("Lưu thay đổi phụ đề trước khi dịch lại");
      return;
    }
    setSubtitleError("");
    try {
      const job = await api.translate(video.id, settings?.target_language);
      trackJob(job);
    } catch (error) {
      setSubtitleError(
        error instanceof Error ? error.message : "Không bắt đầu được job dịch",
      );
    }
  }

  function stopVoicePreview() {
    const current = previewAudio.current;
    if (!current) return;
    current.audio.pause();
    URL.revokeObjectURL(current.url);
    previewAudio.current = null;
  }

  function releasePreview(audio: HTMLAudioElement, url: string) {
    audio.pause();
    URL.revokeObjectURL(url);
    if (previewAudio.current?.audio === audio) {
      previewAudio.current = null;
    }
  }

  function changeTtsVoice(value: string) {
    voiceTouched.current = true;
    setTtsVoice(value);
    setVoiceError("");
    stopVoicePreview();
  }

  function changeTtsRate(value: string) {
    voiceTouched.current = true;
    setTtsRate(value);
    setVoiceError("");
    stopVoicePreview();
  }

  async function handlePreviewVoice() {
    const text = subtitleDraft.find((segment) => segment.text.trim());
    if (!text) {
      setVoiceError("Chưa có câu phụ đề để nghe thử");
      return;
    }
    stopVoicePreview();
    setPreviewing(true);
    setVoiceError("");
    try {
      const blob = await api.previewTts(text.text.trim(), ttsVoice, ttsRate);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      previewAudio.current = { audio, url };
      audio.onended = () => releasePreview(audio, url);
      audio.onerror = () => {
        releasePreview(audio, url);
        setVoiceError("Không phát được audio nghe thử");
      };
      await audio.play();
    } catch (error) {
      stopVoicePreview();
      setVoiceError(
        error instanceof Error ? error.message : "Không tạo được audio nghe thử",
      );
    } finally {
      setPreviewing(false);
    }
  }

  async function handleGenerateVoice() {
    if (!video) return;
    if (subtitleDirtyRef.current) {
      setVoiceError("Lưu thay đổi phụ đề trước khi tạo giọng đọc");
      return;
    }
    setVoiceError("");
    try {
      const job = await api.generateVoice(video.id, {
        voice: ttsVoice,
        rate: ttsRate,
      });
      trackJob(job);
    } catch (error) {
      setVoiceError(
        error instanceof Error ? error.message : "Không bắt đầu được job giọng đọc",
      );
    }
  }

  async function handleDelete() {
    if (!video) return;
    const confirmed = window.confirm(
      `Xoá "${video.title || video.id}"?\nFile trong thư mục video cũng sẽ bị xoá.`,
    );
    if (!confirmed) return;
    setDeleting(true);
    setActionError("");
    try {
      await api.deleteVideo(video.id);
      navigate("/");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Xoá thất bại");
      setDeleting(false);
    }
  }

  async function handleOpenFolder() {
    if (!video) return;
    setActionError("");
    try {
      await api.openFolder(video.id);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Không mở được thư mục",
      );
    }
  }

  async function handleRender() {
    if (!video) return;
    setStartingRender(true);
    setRenderError("");
    try {
      const job = await api.render(video.id, options);
      trackJob(job);
    } catch (error) {
      setRenderError(
        error instanceof Error ? error.message : "Không bắt đầu render được",
      );
    } finally {
      setStartingRender(false);
    }
  }

  if (!video && !loadError) {
    return (
      <div className="grid place-items-center py-24">
        <SpinnerIcon className="size-6 animate-spin text-acid" />
      </div>
    );
  }

  if (!video) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-line bg-panel/60 px-6 py-10 text-center">
        <AlertIcon className="mx-auto size-7 text-rose-300" />
        <p className="mt-3 text-sm font-medium text-zinc-200">
          Không tìm thấy video
        </p>
        <p className="mt-1 text-[12px] text-zinc-500">{loadError}</p>
        <Link
          to="/"
          className="mt-5 inline-flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-[12px] text-zinc-300 transition hover:border-zinc-600"
        >
          <ArrowLeftIcon className="size-3.5" />
          Về thư viện
        </Link>
      </div>
    );
  }

  const steps: Array<{ label: string; done: boolean }> = [
    { label: "Phụ đề", done: video.has_subtitle },
    { label: "Giọng đọc", done: video.has_voice },
    { label: "Bản final", done: video.has_output },
  ];
  const activeJob =
    jobs.find((job) => job.status === "pending" || job.status === "running") ??
    null;
  const pendingJob = pendingJobId
    ? jobs.find((job) => job.id === pendingJobId) ?? null
    : null;
  const visibleJob =
    activeJob ??
    (pendingJob?.status === "failed" ? pendingJob : null);
  const subtitleBusy =
    activeJob?.type === "transcribe" || activeJob?.type === "translate";
  const voiceBusy = activeJob?.type === "tts";
  const previewText =
    subtitleDraft.find((segment) => segment.text.trim())?.text.trim() ?? "";
  const outputUrl = api.fileUrl(video.id, "output", outputVersion);
  const renderDisabled =
    startingRender || activeJob !== null || video.status !== "ready";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface/60 px-3 py-1.5 text-[12px] font-medium text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-200"
        >
          <ArrowLeftIcon className="size-3.5" />
          Thư viện
        </Link>
        <span className="text-zinc-700">/</span>
        <span className="truncate font-mono text-[11px] text-zinc-600">
          {video.id}
        </span>
        <span
          className={`ml-auto rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset ${platformStyle(
            video.platform,
          )}`}
        >
          {platformLabel(video.platform)}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <div className="overflow-hidden rounded-2xl border border-line bg-black">
            {video.status === "ready" ? (
              <video
                key={`${variant}-${outputVersion}`}
                controls
                playsInline
                preload="metadata"
                poster={api.thumbUrl(video.id)}
                src={variant === "output" ? outputUrl : api.fileUrl(video.id, "original")}
                className="max-h-[68vh] w-full bg-black"
              />
            ) : video.status === "downloading" ? (
              <div className="grid aspect-video place-items-center bg-[radial-gradient(circle_at_50%_35%,rgba(215,254,79,0.08),transparent_60%)]">
                <div className="text-center">
                  <SpinnerIcon className="mx-auto size-6 animate-spin text-acid" />
                  <p className="mt-3 text-[12.5px] text-zinc-400">
                    Đang tải video...
                  </p>
                  <p className="mt-1 text-[11px] text-zinc-600">
                    Theo dõi tiến độ ở trang thư viện.
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid aspect-video place-items-center bg-rose-500/[0.04] px-6 text-center">
                <div>
                  <AlertIcon className="mx-auto size-6 text-rose-300" />
                  <p className="mt-3 text-[12.5px] text-zinc-300">
                    Video tải thất bại
                  </p>
                  {video.error && (
                    <p className="mx-auto mt-1 max-w-md text-[11px] leading-relaxed text-rose-300">
                      {video.error}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex w-fit items-center gap-1 rounded-xl border border-line bg-panel/60 p-1">
              <VariantButton
                active={variant === "original"}
                onClick={() => setVariant("original")}
              >
                Original
              </VariantButton>
              <VariantButton
                active={variant === "output"}
                disabled={!video.has_output}
                onClick={() => setVariant("output")}
              >
                Bản final
              </VariantButton>
            </div>
            {video.has_output && (
              <a
                href={outputUrl}
                download={`${video.id}-final.mp4`}
                className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface/70 px-3 py-2 text-[12px] font-medium text-zinc-300 transition hover:border-acid/40 hover:text-white"
              >
                <DownloadIcon className="size-3.5" />
                Tải bản final
              </a>
            )}
          </div>

          {visibleJob && (
            <JobCard
              job={visibleJob}
              onDismiss={
                visibleJob.status === "failed"
                  ? () => setPendingJobId(null)
                  : undefined
              }
            />
          )}

          {actionError && (
            <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300">
              {actionError}
            </p>
          )}
          {renderError && (
            <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300">
              {renderError}
            </p>
          )}

          <SubtitleEditor
            data={subtitle}
            draft={subtitleDraft}
            targetLanguage={settings?.target_language ?? "vi"}
            loading={subtitleLoading}
            busy={subtitleBusy}
            saving={subtitleSaving}
            dirty={subtitleDirty}
            error={subtitleError}
            disabled={video.status !== "ready"}
            onChange={changeSubtitle}
            onAdd={addSubtitleRow}
            onDelete={deleteSubtitleRow}
            onSave={() => void handleSaveSubtitle()}
            onTranscribe={(translate) => void handleTranscribe(translate)}
            onTranslate={() => void handleTranslate()}
          />

          <VoicePanel
            hasSubtitle={video.has_subtitle}
            hasVoice={video.has_voice}
            dirty={subtitleDirty}
            voice={ttsVoice}
            rate={ttsRate}
            previewText={previewText}
            previewing={previewing}
            busy={voiceBusy}
            disabled={
              video.status !== "ready" ||
              (activeJob !== null && activeJob.type !== "tts")
            }
            error={voiceError}
            onVoiceChange={changeTtsVoice}
            onRateChange={changeTtsRate}
            onPreview={() => void handlePreviewVoice()}
            onGenerate={() => void handleGenerateVoice()}
          />
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-line bg-panel/60 p-5">
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <StatusDot status={video.status} />
              <span className="tabular-nums text-zinc-600">
                {formatDate(video.created_at)}
              </span>
            </div>

            <h1 className="mt-3 text-lg font-semibold leading-snug tracking-tight text-white">
              {video.title || "Chưa có tiêu đề"}
            </h1>

            <a
              href={video.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1.5 inline-flex max-w-full items-center gap-1.5 text-[11.5px] text-zinc-500 transition hover:text-acid"
            >
              <ExternalLinkIcon className="size-3 shrink-0" />
              <span className="truncate">Link gốc</span>
            </a>

            <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line/70 pt-4 text-[12px]">
              <div>
                <dt className="text-zinc-600">Thời lượng</dt>
                <dd className="mt-0.5 font-medium tabular-nums text-zinc-200">
                  {formatDuration(video.duration_sec)}
                </dd>
              </div>
              <div>
                <dt className="text-zinc-600">Độ phân giải</dt>
                <dd className="mt-0.5 font-medium tabular-nums text-zinc-200">
                  {formatResolution(video.width, video.height)}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-zinc-600">Nguồn</dt>
                <dd
                  className="mt-0.5 truncate text-zinc-200"
                  title={video.source_url}
                >
                  {video.source_url}
                </dd>
              </div>
            </dl>

            {video.error && (
              <p className="mt-4 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rose-300">
                {video.error}
              </p>
            )}

            <div className="mt-5 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => void handleOpenFolder()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-surface/70 px-3 py-2 text-[12.5px] font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-white"
              >
                <FolderIcon className="size-4" />
                Mở thư mục
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.06] px-3 py-2 text-[12.5px] font-medium text-rose-300 transition hover:border-rose-500/40 hover:bg-rose-500/10 disabled:opacity-50"
              >
                <TrashIcon className="size-4" />
                {deleting ? "Đang xoá..." : "Xoá video"}
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-surface/50 p-5">
            <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">
              Render bản final
            </p>
            <ul className="mt-3 space-y-2 text-[12px]">
              {steps.map((step) => (
                <li
                  key={step.label}
                  className="flex items-center gap-2 text-zinc-500"
                >
                  {step.done ? (
                    <CheckIcon className="size-3.5 text-emerald-400" />
                  ) : (
                    <XIcon className="size-3.5 text-zinc-700" />
                  )}
                  {step.label}
                </li>
              ))}
            </ul>

            <div className="mt-4 space-y-2">
              <OptionToggle
                label="Logo"
                hint={
                  settings?.logo_path
                    ? "Theo cấu hình trong Cài đặt"
                    : "Chưa upload logo trong Cài đặt"
                }
                checked={options.logo}
                disabled={!settings?.logo_path}
                onChange={(checked) => changeOptions({ logo: checked })}
              />
              <OptionToggle
                label="Phụ đề"
                hint={
                  video.has_subtitle
                    ? "Burn phụ đề đã tạo"
                    : "Tạo phụ đề trước khi render"
                }
                checked={options.subtitle}
                disabled={!video.has_subtitle}
                onChange={(checked) => changeOptions({ subtitle: checked })}
              />
              <OptionToggle
                label="Giọng đọc"
                hint={
                  video.has_voice
                    ? "Ghép voice.mp3 vào timeline"
                    : "Tạo giọng đọc trước khi render"
                }
                checked={options.voice}
                disabled={!video.has_voice}
                onChange={(checked) => changeOptions({ voice: checked })}
              />
            </div>

            <label className="mt-3 block">
              <span className="mb-1 block text-[10.5px] uppercase tracking-[0.14em] text-zinc-600">
                Âm thanh gốc
              </span>
              <select
                value={options.keep_original_audio}
                disabled={!options.voice}
                onChange={(event) =>
                  changeOptions({
                    keep_original_audio: event.target.value as AudioMode,
                  })
                }
                className="w-full rounded-xl border border-line bg-ink/60 px-3 py-2 text-[12px] text-zinc-200 outline-none transition disabled:opacity-45 focus:border-acid/50"
              >
                {AUDIO_MODES.map((mode) => (
                  <option key={mode.value} value={mode.value}>
                    {mode.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={() => void handleRender()}
              disabled={renderDisabled}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-acid px-4 py-2.5 text-[12.5px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
            >
              {startingRender || activeJob?.type === "render" ? (
                <SpinnerIcon className="size-4 animate-spin" />
              ) : (
                <DownloadIcon className="size-4 rotate-180" />
              )}
              {activeJob?.type === "render"
                ? "Đang render..."
                : startingRender
                  ? "Đang bắt đầu..."
                  : "Render bản final"}
            </button>
            <p className="mt-2 text-[10.5px] leading-relaxed text-zinc-600">
              Một lệnh ffmpeg duy nhất. Bản gốc luôn được giữ nguyên.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
