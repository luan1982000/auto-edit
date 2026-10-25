import { useRef, useState } from "react";

import type { CoverRegion, SampleFrame } from "../api";

export const DEFAULT_COVER_REGION: CoverRegion = {
  x: 0.05,
  y: 0.78,
  width: 0.9,
  height: 0.15,
};

const PRESETS: Array<{ label: string; region: CoverRegion }> = [
  {
    label: "Dải dưới",
    region: DEFAULT_COVER_REGION,
  },
  {
    label: "Dải trên",
    region: { x: 0.05, y: 0.07, width: 0.9, height: 0.15 },
  },
  {
    label: "Giữa khung",
    region: { x: 0.05, y: 0.425, width: 0.9, height: 0.15 },
  },
];

const MIN_SIZE = 0.01;

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}

interface Point {
  x: number;
  y: number;
}

function rectFromPoints(start: Point, end: Point): CoverRegion {
  const x = Math.min(Math.min(start.x, end.x), 1 - MIN_SIZE);
  const y = Math.min(Math.min(start.y, end.y), 1 - MIN_SIZE);
  const width = Math.min(
    Math.max(Math.abs(end.x - start.x), MIN_SIZE),
    1 - x,
  );
  const height = Math.min(
    Math.max(Math.abs(end.y - start.y), MIN_SIZE),
    1 - y,
  );
  return {
    x: Number(x.toFixed(4)),
    y: Number(y.toFixed(4)),
    width: Number(width.toFixed(4)),
    height: Number(height.toFixed(4)),
  };
}

interface FrameRegionPickerProps {
  frames: SampleFrame[];
  region: CoverRegion | null;
  disabled?: boolean;
  onChange: (region: CoverRegion | null) => void;
}

export function FrameRegionPicker({
  frames,
  region,
  disabled = false,
  onChange,
}: FrameRegionPickerProps) {
  const [active, setActive] = useState(0);
  const [draft, setDraft] = useState<CoverRegion | null>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const dragStart = useRef<Point | null>(null);

  const activeFrame = frames[Math.min(active, frames.length - 1)] ?? null;
  const shown = draft ?? region;

  function pointFromEvent(
    event: React.PointerEvent<HTMLDivElement>,
  ): Point | null {
    const rect = surfaceRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    return {
      x: clamp((event.clientX - rect.left) / rect.width),
      y: clamp((event.clientY - rect.top) / rect.height),
    };
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (disabled) return;
    const point = pointFromEvent(event);
    if (!point) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStart.current = point;
    setDraft({
      x: point.x,
      y: point.y,
      width: MIN_SIZE,
      height: MIN_SIZE,
    });
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStart.current || disabled) return;
    const point = pointFromEvent(event);
    if (!point) return;
    setDraft(rectFromPoints(dragStart.current, point));
  }

  function finishDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStart.current) return;
    const point = pointFromEvent(event);
    const next = point ? rectFromPoints(dragStart.current, point) : draft;
    dragStart.current = null;
    setDraft(null);
    if (
      next &&
      (next.width > MIN_SIZE + 0.001 || next.height > MIN_SIZE + 0.001)
    ) {
      onChange(next);
    }
  }

  function cancelDrag() {
    dragStart.current = null;
    setDraft(null);
  }

  if (!activeFrame) return null;

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12px] font-medium text-zinc-200">
          Vị trí phụ đề cũ trong video
        </p>
        <p className="text-[10.5px] text-zinc-600">
          Kéo chuột trên ảnh để khoanh vùng cần che
        </p>
      </div>

      <div className="mt-2.5 flex gap-2">
        {frames.map((frame, index) => (
          <button
            key={frame.url}
            type="button"
            onClick={() => setActive(index)}
            aria-label={`Xem khung hình tại ${frame.time}s`}
            aria-pressed={index === active}
            className={`group relative w-1/3 overflow-hidden rounded-lg border transition ${
              index === active
                ? "border-acid/70 ring-1 ring-acid/30"
                : "border-line/70 opacity-70 hover:opacity-100"
            }`}
          >
            <img
              src={frame.url}
              alt=""
              draggable={false}
              className="block aspect-video w-full object-cover"
            />
            <span className="absolute bottom-1 left-1 rounded bg-ink/80 px-1.5 py-0.5 font-mono text-[9.5px] text-zinc-300">
              {frame.time.toFixed(1)}s
            </span>
          </button>
        ))}
      </div>

      <div
        ref={surfaceRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishDrag}
        onPointerCancel={cancelDrag}
        className={`relative mt-2.5 touch-none select-none overflow-hidden rounded-xl border border-line/70 bg-black ${
          disabled ? "cursor-default opacity-60" : "cursor-crosshair"
        }`}
      >
        <img
          key={activeFrame.url}
          src={activeFrame.url}
          alt={`Khung hình tại ${activeFrame.time}s`}
          draggable={false}
          className="block w-full"
        />
        {shown ? (
          <div
            className="pointer-events-none absolute border-2 border-acid bg-acid/25 shadow-[0_0_0_9999px_rgba(4,6,8,0.28)]"
            style={{
              left: `${shown.x * 100}%`,
              top: `${shown.y * 100}%`,
              width: `${shown.width * 100}%`,
              height: `${shown.height * 100}%`,
            }}
          >
            <span className="absolute -top-0.5 left-1 rounded-b bg-acid px-1 py-0.5 text-[9px] font-semibold text-ink">
              CHE
            </span>
          </div>
        ) : (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-ink/30">
            <span className="rounded-lg bg-ink/80 px-3 py-1.5 text-[11px] text-zinc-300">
              Chưa chọn vùng che — kéo chuột để chọn
            </span>
          </div>
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            disabled={disabled}
            onClick={() => onChange(preset.region)}
            className="rounded-lg border border-line px-2.5 py-1 text-[10.5px] text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {preset.label}
          </button>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(null)}
          className={`rounded-lg border px-2.5 py-1 text-[10.5px] transition disabled:cursor-not-allowed disabled:opacity-40 ${
            region === null
              ? "border-acid/50 bg-acid/10 text-acid"
              : "border-line text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
          }`}
        >
          Không che
        </button>
        {shown && (
          <span className="ml-auto font-mono text-[10px] tabular-nums text-zinc-600">
            x {(shown.x * 100).toFixed(0)}% · y {(shown.y * 100).toFixed(0)}% ·{" "}
            {(shown.width * 100).toFixed(0)}×{(shown.height * 100).toFixed(0)}%
          </span>
        )}
      </div>
    </div>
  );
}
