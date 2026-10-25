import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, type DuplicateInfo, type Job, type Video } from "../api";
import { JobCard } from "../components/JobCard";
import { VideoCard } from "../components/VideoCard";
import {
  AlertIcon,
  DownloadIcon,
  FolderIcon,
  RefreshIcon,
  SpinnerIcon,
} from "../components/Icons";

export function Home() {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [duplicates, setDuplicates] = useState<DuplicateInfo[]>([]);
  const [videos, setVideos] = useState<Video[]>([]);
  const [videosLoading, setVideosLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [dismissedJobs, setDismissedJobs] = useState<Set<string>>(new Set());

  const urls = useMemo(
    () =>
      text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    [text],
  );

  const refreshVideos = useCallback(async () => {
    try {
      setVideos(await api.videos());
    } catch {
      // Keep the previous list; the poll below will retry.
    } finally {
      setVideosLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshVideos();
  }, [refreshVideos]);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await api.jobs();
        if (alive) setJobs(next);
      } catch {
        // Backend may still be starting.
      }
    };
    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, 1500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const finishedSignature = useMemo(
    () =>
      jobs
        .filter((job) => job.status === "done" || job.status === "failed")
        .map((job) => `${job.id}:${job.status}`)
        .join("|"),
    [jobs],
  );
  const previousSignature = useRef("");
  useEffect(() => {
    if (finishedSignature && finishedSignature !== previousSignature.current) {
      previousSignature.current = finishedSignature;
      void refreshVideos();
    }
  }, [finishedSignature, refreshVideos]);

  const activeJobs = jobs
    .filter((job) => job.status === "pending" || job.status === "running")
    .slice(0, 8);
  const failedJobs = jobs
    .filter((job) => job.status === "failed" && !dismissedJobs.has(job.id))
    .slice(0, 3);

  async function submit(force = false, onlyUrls?: string[]) {
    const target = onlyUrls ?? urls;
    if (!target.length || submitting) return;
    setSubmitting(true);
    setFormError("");
    try {
      const response = await api.download(target, force);
      setDuplicates(response.duplicates);
      setText("");
      if (response.jobs.length > 0) {
        void refreshVideos();
      }
    } catch (error) {
      setFormError(
        error instanceof Error ? error.message : "Không gửi được yêu cầu",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function manualRefresh() {
    setRefreshing(true);
    await refreshVideos();
    window.setTimeout(() => setRefreshing(false), 250);
  }

  function dismissJob(jobId: string) {
    setDismissedJobs((previous) => new Set(previous).add(jobId));
  }

  return (
    <div className="space-y-10">
      <section className="relative overflow-hidden rounded-3xl border border-line bg-panel/70">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-28 size-72 rounded-full bg-acid/10 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-24 left-1/3 size-56 rounded-full bg-cyan-400/5 blur-3xl"
        />
        <div className="relative grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-ink/60 px-3 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-400">
              <span className="size-1.5 rounded-full bg-acid" />
              Local · Không tài khoản
            </span>
            <h1 className="mt-4 text-3xl font-semibold leading-[1.08] tracking-tight text-white sm:text-[2.6rem]">
              Tải video về máy.
              <br />
              <span className="text-acid">Sạch sẽ, cục bộ.</span>
            </h1>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-zinc-400">
              Dán link{" "}
              <span className="text-zinc-200">
                Facebook Reel, Douyin, TikTok, YouTube Shorts
              </span>{" "}
              — mỗi dòng một link. Video lưu trong{" "}
              <code className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-zinc-300">
                data/videos/
              </code>{" "}
              và sẵn sàng để thêm phụ đề, giọng đọc, logo ở các bước sau.
            </p>
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
            className="rounded-2xl border border-line bg-ink/60 p-4 shadow-[0_20px_60px_-40px_rgba(0,0,0,0.9)]"
          >
            <label
              htmlFor="urls"
              className="mb-2 flex items-center justify-between text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-500"
            >
              <span>Danh sách link</span>
              <span className="normal-case tracking-normal text-zinc-600">
                {urls.length} link
              </span>
            </label>
            <textarea
              id="urls"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={5}
              spellCheck={false}
              placeholder={
                "https://www.facebook.com/reel/...\nhttps://v.douyin.com/...\nhttps://www.youtube.com/shorts/..."
              }
              className="w-full resize-none rounded-xl border border-line bg-surface/80 px-3.5 py-3 font-mono text-[12.5px] leading-relaxed text-zinc-200 outline-none transition placeholder:text-zinc-700 focus:border-acid/50 focus:ring-2 focus:ring-acid/10"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-[11px] text-zinc-600">Chỉ hỗ trợ http/https</p>
              <button
                type="submit"
                disabled={urls.length === 0 || submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-acid px-4 py-2.5 text-[13px] font-semibold text-ink transition hover:bg-acid-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting ? (
                  <SpinnerIcon className="size-4 animate-spin" />
                ) : (
                  <DownloadIcon className="size-4" />
                )}
                {submitting ? "Đang gửi..." : "Tải video"}
              </button>
            </div>
            {formError && (
              <p className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300">
                {formError}
              </p>
            )}
          </form>
        </div>
      </section>

      {duplicates.length > 0 && (
        <section className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.07] p-4 sm:p-5">
          <div className="flex items-start gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-amber-400/15 text-amber-300">
              <AlertIcon className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-amber-100">
                {duplicates.length} link đã có trong thư viện
              </p>
              <ul className="mt-2 space-y-1.5">
                {duplicates.map((duplicate) => (
                  <li
                    key={duplicate.video_id}
                    className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-amber-200/80"
                  >
                    <Link
                      to={`/videos/${duplicate.video_id}`}
                      className="truncate font-medium underline decoration-amber-300/30 underline-offset-2 hover:text-amber-100"
                    >
                      {duplicate.title || duplicate.url}
                    </Link>
                    <span className="text-[10px] uppercase tracking-wider text-amber-300/60">
                      {duplicate.status}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() =>
                    void submit(
                      true,
                      duplicates.map((duplicate) => duplicate.url),
                    )
                  }
                  disabled={submitting}
                  className="rounded-lg bg-amber-300 px-3 py-1.5 text-[12px] font-semibold text-amber-950 transition hover:bg-amber-200 disabled:opacity-50"
                >
                  Vẫn tải lại
                </button>
                <button
                  type="button"
                  onClick={() => setDuplicates([])}
                  className="rounded-lg border border-amber-300/20 px-3 py-1.5 text-[12px] font-medium text-amber-200/80 transition hover:bg-amber-300/10"
                >
                  Bỏ qua
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {(activeJobs.length > 0 || failedJobs.length > 0) && (
        <section>
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                Hàng đợi
              </p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-white">
                Đang xử lý{" "}
                {activeJobs.length > 0 && (
                  <span className="ml-1 text-sm font-normal text-zinc-500">
                    ({activeJobs.length})
                  </span>
                )}
              </h2>
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {activeJobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
            {failedJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onDismiss={() => dismissJob(job.id)}
              />
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
              Thư viện
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-white">
              Video đã tải{" "}
              <span className="ml-1 text-sm font-normal text-zinc-500">
                ({videos.length})
              </span>
            </h2>
          </div>
          <button
            type="button"
            onClick={() => void manualRefresh()}
            className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface/60 px-3 py-1.5 text-[12px] font-medium text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-200"
          >
            <RefreshIcon
              className={`size-3.5 ${refreshing ? "animate-spin" : ""}`}
            />
            Làm mới
          </button>
        </div>

        <div className="mt-4">
          {videosLoading ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {[0, 1, 2, 3].map((index) => (
                <div
                  key={index}
                  className="h-52 animate-pulse rounded-2xl border border-line bg-panel/40"
                />
              ))}
            </div>
          ) : videos.length === 0 ? (
            <div className="grid place-items-center rounded-3xl border border-dashed border-line bg-surface/40 px-6 py-16 text-center">
              <span className="grid size-14 place-items-center rounded-2xl border border-line bg-panel text-zinc-600">
                <FolderIcon className="size-6" />
              </span>
              <p className="mt-4 text-sm font-medium text-zinc-300">
                Thư viện đang trống
              </p>
              <p className="mt-1 max-w-xs text-[12.5px] leading-relaxed text-zinc-500">
                Dán link ở khung phía trên và bấm “Tải video”. Video đầu tiên sẽ
                xuất hiện ở đây kèm thumbnail.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {videos.map((video) => (
                <VideoCard key={video.id} video={video} />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
