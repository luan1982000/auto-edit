import type { Job } from "../api";
import { JOB_TYPE_LABELS } from "../lib/format";
import { AlertIcon, CheckIcon, SpinnerIcon, XIcon } from "./Icons";

export function JobCard({
  job,
  onDismiss,
}: {
  job: Job;
  onDismiss?: () => void;
}) {
  const active = job.status === "pending" || job.status === "running";
  const failed = job.status === "failed";
  const title = JOB_TYPE_LABELS[job.type] ?? job.type;
  const url = typeof job.params.url === "string" ? job.params.url : "";

  return (
    <div
      className={`rounded-2xl border p-4 ${
        failed
          ? "border-rose-500/25 bg-rose-500/[0.06]"
          : "border-line bg-panel/60"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg ${
            failed ? "bg-rose-500/15 text-rose-300" : "bg-acid/10 text-acid"
          }`}
        >
          {active ? (
            <SpinnerIcon className="size-4 animate-spin" />
          ) : failed ? (
            <AlertIcon className="size-4" />
          ) : (
            <CheckIcon className="size-4" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-[13px] font-medium text-zinc-100">{title}</p>
            <span className="ml-auto shrink-0 text-[11px] tabular-nums text-zinc-500">
              {failed ? "Thất bại" : `${job.progress}%`}
            </span>
            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                aria-label="Ẩn thông báo"
                className="-mr-1 rounded-md p-1 text-zinc-600 transition hover:bg-white/5 hover:text-zinc-300"
              >
                <XIcon className="size-3.5" />
              </button>
            )}
          </div>

          {url && (
            <p className="mt-0.5 truncate text-[11px] text-zinc-600">{url}</p>
          )}

          {active && (
            <>
              <p className="mt-1 truncate text-[11px] text-zinc-500">
                {job.message || "Chờ xử lý..."}
              </p>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-acid transition-all duration-500"
                  style={{ width: `${Math.max(job.progress, 2)}%` }}
                />
              </div>
            </>
          )}

          {failed && job.error && (
            <p className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-rose-950/40 px-2.5 py-2 text-[11px] leading-relaxed text-rose-200">
              {job.error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
