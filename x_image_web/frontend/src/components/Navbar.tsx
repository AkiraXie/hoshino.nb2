import { Link, useLocation } from "react-router-dom";
import { useState } from "react";

export default function Navbar() {
  const location = useLocation();
  const [search, setSearch] = useState("");

  const isActive = (path: string) =>
    location.pathname === path
      ? "text-accent-light border-accent"
      : "text-text-secondary hover:text-text-primary border-transparent";

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (search.trim()) {
      window.location.href = `/?q=${encodeURIComponent(search.trim())}`;
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-bg-secondary/80 backdrop-blur-xl border-b border-border">
      <div className="max-w-[1600px] mx-auto px-4 h-14 flex items-center justify-between gap-4">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 no-underline shrink-0">
          <span className="text-xl font-bold text-accent-light tracking-tight">
            ✕ Gallery
          </span>
        </Link>

        {/* Nav links */}
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
          <Link to="/" className={`no-underline border-b-2 pb-0.5 transition-colors ${isActive("/")}`}>
            首页
          </Link>
          <Link to="/uids" className={`no-underline border-b-2 pb-0.5 transition-colors ${isActive("/uids")}`}>
            用户
          </Link>
          <Link to="/favorites" className={`no-underline border-b-2 pb-0.5 transition-colors ${isActive("/favorites")}`}>
            收藏
          </Link>
        </nav>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索内容或用户..."
            className="bg-bg-card border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary
                       placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                       w-40 md:w-56 transition-all"
          />
          <button
            type="submit"
            className="bg-accent hover:bg-accent-dark text-white rounded-lg px-3 py-1.5 text-sm font-medium
                       transition-colors cursor-pointer"
          >
            搜索
          </button>
        </form>
      </div>
    </header>
  );
}
