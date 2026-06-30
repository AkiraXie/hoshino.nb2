import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useState, useCallback, useEffect, useRef, type ReactNode } from "react";
import { refreshIndex } from "../api";

export default function Navbar() {
  const [searchParams] = useSearchParams();
  const [input, setInput] = useState(searchParams.get("q") || "");
  const [searchOpen, setSearchOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setInput(searchParams.get("q") || "");
  }, [searchParams]);

  useEffect(() => {
    setIsSidebarOpen(false);
    setSearchOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!isSidebarOpen) {
      document.body.style.overflow = "";
      return;
    }
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isSidebarOpen]);

  useEffect(() => {
    if (searchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [searchOpen]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const q = input.trim();
      navigate(q ? `/?q=${encodeURIComponent(q)}` : "/");
      setSearchOpen(false);
    },
    [input, navigate]
  );

  const handleRefresh = useCallback(async () => {
    await refreshIndex();
    window.location.reload();
  }, []);

  return (
    <>
      {/* ── Top Header ── */}
      <header
        className="fixed top-0 right-0 left-0 md:left-[260px] h-[60px] z-[99] flex items-center justify-end px-3 md:px-10
                   bg-white/85 backdrop-blur-[10px] border-b-2 border-transparent
                   transition-[left] duration-300"
      >
        {/* Mobile leading area */}
        <div className="hidden max-md:flex items-center gap-2.5 min-w-0">
          <button
            type="button"
            className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-surface border border-border text-text"
            onClick={() => setIsSidebarOpen(true)}
            aria-label="打开导航"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="7" x2="20" y2="7" />
              <line x1="4" y1="12" x2="20" y2="12" />
              <line x1="4" y1="17" x2="20" y2="17" />
            </svg>
          </button>

          {/* Mobile search */}
          <div className="hidden max-md:flex items-center">
            {searchOpen ? (
              <form className="flex items-center gap-1.5" onSubmit={(e) => { handleSubmit(e); }}>
                <input
                  type="text"
                  placeholder="搜索..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  autoFocus
                  className="w-[160px] h-9 border border-primary rounded-full px-3 text-sm outline-none font-medium bg-surface"
                  onBlur={() => { if (!input.trim()) setSearchOpen(false); }}
                />
                <button type="button" className="flex items-center justify-center w-7 h-7 rounded-full bg-transparent text-text-secondary hover:bg-border transition-colors" onClick={() => setSearchOpen(false)}>
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </form>
            ) : (
              <button className="flex items-center justify-center w-9 h-9 rounded-full border border-border bg-surface text-text hover:bg-primary-light hover:border-primary hover:text-primary transition-all" onClick={() => setSearchOpen(true)} aria-label="打开搜索">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
              </button>
            )}
          </div>

          {/* Mobile refresh */}
          <button
            className="flex items-center justify-center w-9 h-9 rounded-full border border-border bg-surface text-text hover:bg-primary-light hover:border-primary hover:text-primary transition-all"
            onClick={handleRefresh}
            aria-label="刷新索引"
          >
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
            </svg>
          </button>
        </div>

        {/* Desktop: search + refresh */}
        <div className="flex items-center gap-2 max-md:hidden">
          {searchOpen ? (
            <form className="flex items-center gap-2" style={{ animation: "searchExpand 0.2s cubic-bezier(0.16,1,0.3,1)" }} onSubmit={(e) => { handleSubmit(e); }}>
              <input
                ref={searchInputRef}
                type="text"
                placeholder="搜索..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onBlur={() => { if (!input.trim()) setSearchOpen(false); }}
                className="w-[180px] h-9 border border-border rounded-full px-4 text-sm outline-none focus:border-primary focus:ring-[3px] focus:ring-primary/10 transition-all font-medium"
              />
              <button type="button" className="w-9 h-9 flex items-center justify-center rounded-full border border-border bg-white hover:bg-surface-hover transition-colors" onClick={() => { setSearchOpen(false); setInput(""); }}>
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </form>
          ) : (
            <button
              className="w-9 h-9 flex items-center justify-center rounded-full border border-border bg-white hover:bg-surface-hover hover:border-primary hover:text-primary transition-all duration-200"
              onClick={() => setSearchOpen(true)}
              aria-label="搜索"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </button>
          )}

          <button
            className="w-9 h-9 flex items-center justify-center rounded-full border border-border bg-white hover:bg-surface-hover hover:text-primary transition-all duration-200"
            onClick={handleRefresh}
            title="重新同步索引"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
            </svg>
          </button>
        </div>
      </header>

      {/* ── Sidebar Backdrop (mobile) ── */}
      {isSidebarOpen && (
        <div
          className="hidden max-md:block fixed inset-0 bg-text/40 backdrop-blur-[2px] z-[100]"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* ── Left Sidebar ── */}
      <aside
        className={`fixed top-0 left-0 bottom-0 w-[260px] bg-surface border-r-2 border-border z-[101]
                    flex flex-col gap-9 overflow-y-auto px-6 py-10
                    max-md:w-[min(82vw,320px)] max-md:px-[18px] max-md:py-6 max-md:gap-6 max-md:border-r
                    transition-transform duration-[260ms] ease-in-out
                    ${isSidebarOpen ? "max-md:translate-x-0 max-md:shadow-[0_24px_48px_rgba(28,27,24,0.22)]" : "max-md:-translate-x-full max-md:shadow-none"}`}
      >
        {/* Brand */}
        <div className="flex items-center justify-between max-md:w-full">
          <Link
            to="/"
            className="text-[22px] font-extrabold text-primary no-underline whitespace-nowrap inline-flex items-center hover:scale-[1.02] transition-transform duration-200"
            onClick={() => setInput("")}
          >
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: "middle", marginRight: "10px", color: "#ff2442" }}>
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
              <circle cx="12" cy="13" r="4"></circle>
            </svg>
            <span>微博图坊</span>
          </Link>

          {/* Mobile close — hidden on desktop */}
          <button
            type="button"
            className="hidden max-md:inline-flex items-center justify-center w-9 h-9 rounded-full bg-bg text-text border-none cursor-pointer shrink-0"
            onClick={() => setIsSidebarOpen(false)}
            aria-label="关闭导航"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Nav groups */}
        <div className="flex flex-col gap-7 max-md:gap-4">
          {[
            {
              title: "发现",
              links: [
                { to: "/", label: "首页推荐", icon: "home", match: (_p: string, _q?: string) => _p === "/" && !_q && !new URLSearchParams(window.location.search).get("uid") },
                { to: "/timeline/today", label: "时光轴", icon: "calendar", match: (_p: string, _q?: string) => _p.startsWith("/timeline") },
                { to: "/top", label: "排行榜", icon: "star", match: (_p: string, _q?: string) => _p === "/top" },
              ],
            },
            {
              title: "分类",
              links: [
                { to: "/uids", label: "知名博主", icon: "users", match: (p: string) => p === "/uids" },
                { to: "/tags", label: "标签分类", icon: "tag", match: (p: string) => p.startsWith("/tags") },
              ],
            },
            {
              title: "个人",
              links: [
                { to: "/favorites", label: "我的收藏", icon: "heart", match: (p: string) => p === "/favorites" },
                { to: "/blacklist", label: "屏蔽列表", icon: "block", match: (p: string) => p === "/blacklist" },
              ],
            },
          ].map((group) => (
            <div key={group.title} className="flex flex-col gap-3 max-md:gap-2">
              <div className="text-[11px] uppercase tracking-[0.12em] text-text-secondary font-extrabold pl-3">
                {group.title}
              </div>
              <div className="flex flex-col gap-1.5 max-md:items-stretch">
                {group.links.map((link) => {
                  const isActive = link.match(location.pathname, searchParams.get("q") || "");
                  const icons: Record<string, ReactNode> = {
                    home: <><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></>,
                    calendar: <><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></>,
                    star: <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path>,
                    users: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></>,
                    tag: <><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path><line x1="7" y1="7" x2="7.01" y2="7"></line></>,
                    heart: <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>,
                    block: <><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></>,
                  };
                  return (
                    <Link
                      key={link.to}
                      to={link.to}
                      className={`flex items-center gap-3 text-sm font-semibold no-underline px-4 py-2.5 rounded-xl transition-all duration-200
                        ${isActive
                          ? "bg-primary-light text-primary"
                          : "text-text-secondary hover:bg-bg hover:text-text"
                        }`}
                    >
                      <svg className={`shrink-0 ${isActive ? "text-primary" : "text-text-secondary"} transition-colors`} viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        {icons[link.icon]}
                      </svg>
                      <span>{link.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
