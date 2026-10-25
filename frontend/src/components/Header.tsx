import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { api, type Health } from "../api";
import { FilmIcon } from "./Icons";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3.5 py-1.5 text-[13px] font-medium transition ${
    isActive
      ? "bg-acid text-ink shadow-[0_4px_18px_-8px] shadow-acid/80"
      : "text-zinc-400 hover:text-zinc-100"
  }`;

export function Header() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((value) => {
        if (alive) setHealth(value);
      })
      .catch(() => {
        // Backend not started yet — the badge simply stays hidden.
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-ink/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-xl bg-acid text-ink shadow-[0_0_26px_-8px] shadow-acid/90">
            <FilmIcon className="size-[18px]" />
          </span>
          <span className="leading-tight">
            <span className="block text-[15px] font-semibold tracking-tight text-zinc-100">
              Reup Studio
            </span>
            <span className="hidden text-[10px] uppercase tracking-[0.2em] text-zinc-500 sm:block">
              Local video toolkit
            </span>
          </span>
        </Link>

        <nav className="ml-auto flex items-center gap-1 rounded-full border border-line bg-surface/70 p-1">
          <NavLink to="/" end className={navLinkClass}>
            Thư viện
          </NavLink>
          <NavLink to="/settings" className={navLinkClass}>
            Cài đặt
          </NavLink>
        </nav>

        {health &&
          (health.problems.length > 0 ? (
            <span
              title={health.problems.join("\n")}
              className="hidden items-center gap-1.5 rounded-full border border-amber-400/25 bg-amber-400/10 px-2.5 py-1 text-[11px] font-medium text-amber-300 sm:flex"
            >
              <span className="size-1.5 rounded-full bg-amber-400" />
              Thiếu công cụ
            </span>
          ) : (
            <span
              title={`yt-dlp ${health.yt_dlp_version ?? ""}`}
              className="hidden items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 sm:flex"
            >
              <span className="size-1.5 rounded-full bg-emerald-400" />
              Sẵn sàng
            </span>
          ))}
      </div>
    </header>
  );
}
