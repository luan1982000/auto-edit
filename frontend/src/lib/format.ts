import type { VideoStatus } from "../api";

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "--:--";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatResolution(width: number, height: number): string {
  if (!width || !height) return "—";
  return `${width} × ${height}`;
}

const PLATFORM_LABELS: Record<string, string> = {
  facebook: "Facebook",
  youtube: "YouTube",
  douyin: "Douyin",
  tiktok: "TikTok",
  upload: "Tải lên",
  other: "Khác",
};

const PLATFORM_STYLES: Record<string, string> = {
  facebook: "bg-blue-500/15 text-blue-300 ring-blue-400/25",
  youtube: "bg-red-500/15 text-red-300 ring-red-400/25",
  douyin: "bg-zinc-100/10 text-zinc-200 ring-white/20",
  tiktok: "bg-cyan-500/15 text-cyan-300 ring-cyan-400/25",
  upload: "bg-emerald-500/15 text-emerald-300 ring-emerald-400/25",
  other: "bg-white/5 text-zinc-300 ring-white/10",
};

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

export function platformStyle(platform: string): string {
  return PLATFORM_STYLES[platform] ?? PLATFORM_STYLES.other;
}

export const VIDEO_STATUS_LABELS: Record<VideoStatus, string> = {
  downloading: "Đang tải",
  ready: "Sẵn sàng",
  failed: "Lỗi",
};

export const JOB_TYPE_LABELS: Record<string, string> = {
  download: "Tải video",
  transcribe: "Tạo phụ đề",
  translate: "Dịch phụ đề",
  tts: "Tạo giọng đọc",
  render: "Render video",
};
