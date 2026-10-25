import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type Video, type VideoStatus } from "../api";
import {
  formatDate,
  formatDuration,
  platformLabel,
  platformStyle,
} from "../lib/format";
import { FilmIcon, PlayIcon, SpinnerIcon } from "./Icons";

export function StatusDot({ status }: { status: VideoStatus }) {
  if (status === "downloading") {
    return (
      <span className="inline-flex items-center gap-1.5 text-acid/90">
        <span className="size-1.5 animate-pulse rounded-full bg-acid" />
        Đang tải
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-rose-300">
        <span className="size-1.5 rounded-full bg-rose-400" />
        Lỗi
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-emerald-300/90">
      <span className="size-1.5 rounded-full bg-emerald-400" />
      Sẵn sàng
    </span>
  );
}

export function VideoCard({ video }: { video: Video }) {
  const [thumbFailed, setThumbFailed] = useState(false);
  const showThumb = video.status === "ready" && !thumbFailed;

  return (
    <Link
      to={`/videos/${video.id}`}
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-line bg-panel/60 transition duration-300 hover:-translate-y-0.5 hover:border-acid/40 hover:bg-panel hover:shadow-[0_18px_40px_-24px] hover:shadow-acid/30"
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-surface">
        {showThumb ? (
          <img
            src={api.thumbUrl(video.id)}
            alt=""
            loading="lazy"
            onError={() => setThumbFailed(true)}
            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div
            className={`flex h-full w-full items-center justify-center ${
              video.status === "failed"
                ? "bg-rose-500/5"
                : "bg-[radial-gradient(circle_at_30%_20%,rgba(215,254,79,0.12),transparent_60%)]"
            }`}
          >
            {video.status === "downloading" ? (
              <SpinnerIcon className="size-6 animate-spin text-acid/70" />
            ) : (
              <FilmIcon className="size-7 text-zinc-700" />
            )}
          </div>
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent" />

        <span
          className={`absolute left-2.5 top-2.5 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset ${platformStyle(
            video.platform,
          )}`}
        >
          {platformLabel(video.platform)}
        </span>

        {video.duration_sec > 0 && (
          <span className="absolute bottom-2.5 right-2.5 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-zinc-200">
            {formatDuration(video.duration_sec)}
          </span>
        )}

        {video.status === "ready" && (
          <span className="absolute inset-0 grid place-items-center opacity-0 transition duration-300 group-hover:opacity-100">
            <span className="grid size-11 place-items-center rounded-full bg-acid/95 pl-0.5 text-ink shadow-[0_8px_30px_rgba(0,0,0,0.45)]">
              <PlayIcon className="size-4" />
            </span>
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3.5">
        <h3 className="line-clamp-2 text-[13.5px] font-medium leading-snug text-zinc-100">
          {video.title || "Đang lấy thông tin..."}
        </h3>
        <div className="mt-auto flex items-center justify-between gap-2 text-[11px] text-zinc-500">
          <StatusDot status={video.status} />
          <span className="truncate tabular-nums">
            {video.width && video.height
              ? `${video.width}×${video.height}`
              : formatDate(video.created_at)}
          </span>
        </div>
      </div>
    </Link>
  );
}
