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
  output_version: number;
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
  logo_position: LogoPosition;
  logo_scale_pct: number;
  logo_opacity: number;
  logo_margin_px: number;
  tts_engine: string;
  tts_voice: string;
  tts_rate: string;
  render_preset: "logo" | "logo_subtitle" | "full";
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

export type LogoPosition = "tl" | "tr" | "bl" | "br";
export type AudioMode = "mute" | "duck" | "keep";

export interface SubtitleSegment {
  start: number;
  end: number;
  text: string;
}

export interface SubtitleData {
  language: string;
  target_language: string;
  translated: boolean;
  segments: SubtitleSegment[];
}

export interface RenderOptions {
  logo: boolean;
  subtitle: boolean;
  voice: boolean;
  keep_original_audio: AudioMode;
}

export interface CoverRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SampleFrame {
  time: number;
  url: string;
}

export interface SampleFramesResponse {
  frames: SampleFrame[];
  region: CoverRegion | null;
}

export interface TranscribeOptions {
  translate: boolean;
  sourceLanguage: string | null;
  targetLanguage: string | null;
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
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
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
  uploadVideo: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Video>("/api/upload", { method: "POST", body });
  },
  openFolder: (id: string) =>
    request<{ opened: boolean }>(`/api/videos/${id}/open-folder`, {
      method: "POST",
    }),

  jobs: (status?: JobStatus, videoId?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (videoId) params.set("video_id", videoId);
    const query = params.toString();
    return request<Job[]>(`/api/jobs${query ? `?${query}` : ""}`);
  },

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

  uploadLogo: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<AppSettings>("/api/settings/logo", { method: "POST", body });
  },
  deleteLogo: () =>
    request<AppSettings>("/api/settings/logo", { method: "DELETE" }),
  logoUrl: (version?: number) =>
    `/api/settings/logo${version ? `?v=${version}` : ""}`,

  render: (id: string, options: RenderOptions) =>
    request<Job>(`/api/videos/${id}/render`, {
      method: "POST",
      body: JSON.stringify(options),
    }),

  subtitle: (id: string) =>
    request<SubtitleData>(`/api/videos/${id}/subtitle`),
  transcribe: (id: string, options: TranscribeOptions) =>
    request<Job>(`/api/videos/${id}/transcribe`, {
      method: "POST",
      body: JSON.stringify({
        translate: options.translate,
        source_language: options.sourceLanguage,
        target_language: options.targetLanguage,
      }),
    }),
  translate: (id: string, targetLanguage?: string) =>
    request<Job>(`/api/videos/${id}/translate`, {
      method: "POST",
      body: JSON.stringify(
        targetLanguage ? { target_language: targetLanguage } : {},
      ),
    }),
  sampleFrames: (id: string) =>
    request<SampleFramesResponse>(`/api/videos/${id}/sample-frames`, {
      method: "POST",
    }),
  coverRegion: (id: string) =>
    request<CoverRegion | null>(`/api/videos/${id}/cover-region`),
  saveCoverRegion: (id: string, region: CoverRegion) =>
    request<CoverRegion>(`/api/videos/${id}/cover-region`, {
      method: "PUT",
      body: JSON.stringify(region),
    }),
  deleteCoverRegion: (id: string) =>
    request<void>(`/api/videos/${id}/cover-region`, { method: "DELETE" }),
  saveSubtitle: (id: string, segments: SubtitleSegment[]) =>
    request<SubtitleData>(`/api/videos/${id}/subtitle`, {
      method: "PUT",
      body: JSON.stringify({ segments }),
    }),
  generateVoice: (id: string, options: { voice: string; rate: string }) =>
    request<Job>(`/api/videos/${id}/tts`, {
      method: "POST",
      body: JSON.stringify(options),
    }),
  previewTts: async (
    text: string,
    voice: string,
    rate: string,
  ): Promise<Blob> => {
    const response = await fetch("/api/tts/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, rate }),
    });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    return response.blob();
  },

  thumbUrl: (id: string) => `/api/videos/${id}/thumb`,
  fileUrl: (id: string, variant: "original" | "output", version?: number) =>
    `/api/videos/${id}/file?variant=${variant}${version ? `&v=${version}` : ""}`,
};
