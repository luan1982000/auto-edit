export type VideoStatus = "downloading" | "ready" | "failed";
export type JobStatus = "pending" | "running" | "done" | "failed";

export interface Video {
  id: string;
  source_url: string;
  platform: string;
  title: string;
  duration_sec: number;
  width: number;
  height: number;
  status: VideoStatus;
  error: string | null;
  has_subtitle: boolean;
  has_voice: boolean;
  has_output: boolean;
  created_at: string;
}

export interface Job {
  id: string;
  video_id: string | null;
  type: string;
  status: JobStatus;
  progress: number;
  message: string;
  error: string | null;
  params: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
}

export interface DuplicateInfo {
  url: string;
  video_id: string;
  title: string;
  status: string;
}

export interface DownloadResponse {
  jobs: Job[];
  duplicates: DuplicateInfo[];
}

export interface AppSettings {
  logo_path: string;
  logo_position: "tl" | "tr" | "bl" | "br";
  logo_scale_pct: number;
  logo_opacity: number;
  logo_margin_px: number;
  tts_engine: string;
  tts_voice: string;
  tts_rate: string;
  subtitle_font: string;
  subtitle_size: number;
  subtitle_position: "bottom" | "top" | "center";
  target_language: string;
  whisper_model: string;
  cookies_browser: string;
}

export interface Health {
  ok: boolean;
  ffmpeg: boolean;
  ffprobe: boolean;
  yt_dlp: boolean;
  yt_dlp_version: string | null;
  problems: string[];
}

export interface UpdateYtdlpResponse {
  ok: boolean;
  output: string;
  version: string | null;
  restart_required: boolean;
}

async function readError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : JSON.stringify(item),
          )
          .join("; ");
      }
    }
  } catch {
    // Not JSON — fall through to the HTTP status.
  }
  return `${response.status} ${response.statusText}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),

  videos: () => request<Video[]>("/api/videos"),
  video: (id: string) => request<Video>(`/api/videos/${id}`),
  deleteVideo: (id: string) =>
    request<void>(`/api/videos/${id}`, { method: "DELETE" }),
  download: (urls: string[], force = false) =>
    request<DownloadResponse>("/api/download", {
      method: "POST",
      body: JSON.stringify({ urls, force }),
    }),
  openFolder: (id: string) =>
    request<{ opened: boolean }>(`/api/videos/${id}/open-folder`, {
      method: "POST",
    }),

  jobs: (status?: JobStatus) =>
    request<Job[]>(`/api/jobs${status ? `?status=${status}` : ""}`),

  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (patch: Partial<AppSettings>) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  updateYtdlp: () =>
    request<UpdateYtdlpResponse>("/api/system/update-ytdlp", {
      method: "POST",
    }),

  thumbUrl: (id: string) => `/api/videos/${id}/thumb`,
  fileUrl: (id: string, variant: "original" | "output") =>
    `/api/videos/${id}/file?variant=${variant}`,
};
