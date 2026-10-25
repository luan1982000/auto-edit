import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, type Video } from "../api";
import {
  AlertIcon,
  ArrowLeftIcon,
  CheckIcon,
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

export function VideoDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [video, setVideo] = useState<Video | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [variant, setVariant] = useState<"original" | "output">("original");

  useEffect(() => {
    if (!id) return;
    let alive = true;
    const load = async () => {
      try {
        const next = await api.video(id);
        if (alive) {
          setVideo(next);
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
    }, 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [id]);

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
                key={variant}
                controls
                playsInline
                preload="metadata"
                poster={api.thumbUrl(video.id)}
                src={api.fileUrl(video.id, variant)}
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

          {actionError && (
            <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300">
              {actionError}
            </p>
          )}
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
                <dd className="mt-0.5 truncate text-zinc-200" title={video.source_url}>
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
              Bước tiếp theo
            </p>
            <p className="mt-2 text-[12px] leading-relaxed text-zinc-500">
              Phụ đề, giọng đọc và render logo sẽ được bật ở các phase tiếp
              theo. Video gốc luôn được giữ nguyên.
            </p>
            <ul className="mt-3 space-y-2 text-[12px]">
              {steps.map((step) => (
                <li key={step.label} className="flex items-center gap-2 text-zinc-500">
                  {step.done ? (
                    <CheckIcon className="size-3.5 text-emerald-400" />
                  ) : (
                    <XIcon className="size-3.5 text-zinc-700" />
                  )}
                  {step.label}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
