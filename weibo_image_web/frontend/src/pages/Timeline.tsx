import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, Link, useNavigationType } from "react-router-dom";
import Masonry from "react-masonry-css";
import PostCard from "../components/PostCard";
import TopUsers from "../components/TopUsers";
import {
  fetchPosts,
  fetchFavoriteIds,
  addFavorite,
  removeFavorite,
} from "../api";
import type { PostSummary } from "../types";
import { saveListCache, loadListCache } from "../hooks/listCache";
import { useScrollRestore } from "../hooks/useScrollMemory";

const TABS = [
  { key: "today", label: "今日" },
  { key: "yesterday", label: "昨日" },
  { key: "older", label: "以往" },
] as const;

type Period = (typeof TABS)[number]["key"];

const BREAKPOINTS = { default: 5, 1400: 4, 1100: 3, 900: 2, 640: 1 };

interface ListData { posts: PostSummary[]; page: number; total: number }

export default function Timeline() {
  const { period } = useParams();
  const navType = useNavigationType();
  const activeTab: Period =
    period === "yesterday" ? "yesterday" : period === "older" ? "older" : "today";

  const routeKey = `timeline:${activeTab}`;
  const cached = useRef(
    navType === "POP" ? loadListCache<ListData>(routeKey) : null
  ).current;

  const [posts, setPosts] = useState<PostSummary[]>(cached?.posts ?? []);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(cached?.page ?? 1);
  const [total, setTotal] = useState(cached?.total ?? 0);
  const [loading, setLoading] = useState(!cached);
  const [showTop, setShowTop] = useState(true);
  const skipFetchRef = useRef(!!cached);

  const loadingRef = useRef(false);
  const canLoadMoreRef = useRef(false);
  const routeKeyRef = useRef(routeKey);

  useEffect(() => { loadingRef.current = loading; }, [loading]);
  useEffect(() => { canLoadMoreRef.current = posts.length < total; }, [posts.length, total]);

  useScrollRestore(posts.length > 0 || (!loading && total === 0));

  useEffect(() => {
    if (routeKeyRef.current !== routeKey) {
      routeKeyRef.current = routeKey;
      skipFetchRef.current = false;
      setPosts([]);
      setPage(1);
      setTotal(0);
      setShowTop(true);
    }
  }, [routeKey]);

  useEffect(() => {
    if (posts.length > 0) saveListCache(routeKey, { posts, page, total });
  }, [posts, page, total, routeKey]);

  useEffect(() => {
    if (skipFetchRef.current) { skipFetchRef.current = false; return; }
    let cancelled = false;
    setLoading(true);
    fetchPosts({ page, size: 90, date: activeTab })
      .then((data) => {
        if (cancelled) return;
        setPosts((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, activeTab]);

  useEffect(() => {
    fetchFavoriteIds().then((ids) => setFavIds(new Set(ids)));
  }, []);

  useEffect(() => {
    function onScroll() {
      if (loadingRef.current || !canLoadMoreRef.current) return;
      if (document.documentElement.scrollHeight - window.scrollY - window.innerHeight < window.innerHeight * 4) {
        setPage((p) => p + 1);
      }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const toggleFav = useCallback(
    async (postUid: string, postId: string) => {
      const key = `${postUid}_${postId}`;
      if (favIds.has(key)) {
        await removeFavorite(postUid, postId);
        setFavIds((prev) => { const s = new Set(prev); s.delete(key); return s; });
      } else {
        await addFavorite(postUid, postId);
        setFavIds((prev) => new Set(prev).add(key));
      }
    },
    [favIds]
  );

  const handleDeleted = useCallback((delUid: string, delId: string) => {
    setPosts((prev) => prev.filter((p) => !(p.uid === delUid && p.id === delId)));
    setTotal((t) => t - 1);
  }, []);

  const handleBlocked = useCallback((blockedUid: string) => {
    setPosts((prev) => {
      const filtered = prev.filter((p) => p.uid !== blockedUid);
      setTotal((t) => t - (prev.length - filtered.length));
      return filtered;
    });
  }, []);

  return (
    <>
      {/* Tab bar — no border, just pill buttons */}
      <div className="flex gap-2 mb-8 overflow-x-auto">
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <Link
              key={tab.key}
              to={`/timeline/${tab.key}`}
              className={`inline-flex items-center px-5 py-2 rounded-full text-sm font-bold no-underline transition-all duration-200 border ${
                active
                  ? "bg-primary border-primary text-white shadow-[0_4px_12px_rgba(255,36,66,0.25)]"
                  : "bg-white border-border text-text-secondary hover:border-primary hover:text-primary hover:bg-primary-light"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      {/* Top 5 bloggers toggle */}
      <section className="mb-8">
        <button
          className="inline-flex items-center gap-1.5 bg-transparent border-none cursor-pointer text-sm font-semibold text-text py-1.5 mb-4 hover:text-primary transition-colors"
          onClick={() => setShowTop((v) => !v)}
        >
          Top 5 活跃博主
          <span className="text-xs text-text-secondary/40 transition-transform" style={{ transform: showTop ? 'rotate(180deg)' : 'rotate(0deg)' }}>▾</span>
        </button>
        {showTop && <TopUsers date={activeTab} />}
      </section>

      {/* Post count header */}
      <div className="flex items-center gap-2.5 mb-6">
        <h2 className="text-lg font-semibold text-text">全部</h2>
        <span className="text-sm text-text-secondary/50 font-medium">
          {total}
        </span>
      </div>

      {/* Masonry grid */}
      <Masonry breakpointCols={BREAKPOINTS} className="masonry-grid" columnClassName="masonry-column">
        {posts.map((post) => (
          <PostCard
            key={`${post.uid}_${post.id}`}
            post={post}
            isFav={favIds.has(`${post.uid}_${post.id}`)}
            onToggleFav={toggleFav}
            onDeleted={handleDeleted}
            onBlocked={handleBlocked}
            hideAuthor
          />
        ))}
      </Masonry>

      {/* Loading / empty state */}
      <div className="flex justify-center py-10 text-text-secondary text-sm">
        {loading && <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />}
        {!loading && posts.length >= total && posts.length > 0 && (
          <span className="text-text-secondary/40 text-xs">没有更多了</span>
        )}
        {!loading && posts.length === 0 && (
          <div className="text-center py-16 text-text-secondary/60">
            <p className="text-sm">该时段暂无微博</p>
          </div>
        )}
      </div>
    </>
  );
}
