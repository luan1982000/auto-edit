import { Link, Route, Routes } from "react-router-dom";

import { Header } from "./components/Header";
import { Home } from "./pages/Home";
import { SettingsPage } from "./pages/Settings";
import { VideoDetail } from "./pages/VideoDetail";

function NotFound() {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-line bg-panel/60 px-6 py-12 text-center">
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-zinc-600">
        404
      </p>
      <h1 className="mt-2 text-lg font-semibold text-zinc-100">
        Trang không tồn tại
      </h1>
      <Link
        to="/"
        className="mt-5 inline-flex rounded-lg bg-acid px-3.5 py-2 text-[12.5px] font-semibold text-ink transition hover:bg-acid-soft"
      >
        Về thư viện
      </Link>
    </div>
  );
}

export default function App() {
  return (
    <div className="relative min-h-screen overflow-x-clip">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,rgba(215,254,79,0.08),transparent_55%),radial-gradient(ellipse_at_bottom_right,rgba(56,189,248,0.06),transparent_50%)]"
      />
      <Header />
      <main className="mx-auto max-w-6xl px-4 pb-20 pt-8 sm:px-6 lg:pt-12">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/videos/:id" element={<VideoDetail />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="border-t border-line/60 py-6 text-center text-[11px] text-zinc-600">
        Chạy local · Dữ liệu nằm trong thư mục data/ · Chỉ dùng cho mục đích cá
        nhân
      </footer>
    </div>
  );
}
