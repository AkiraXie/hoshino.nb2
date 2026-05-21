import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useLocation, useNavigationType } from "react-router-dom";
import Masonry from "react-masonry-css";
import PostCard from "../components/PostCard";
import {
  fetchPosts,
  fetchFavoriteIds,
  addFavorite,
  removeFavorite,
} from "../api";
import type { PostSummary } from "../types";
import { saveListCache, loadListCache } from "../hooks/listCache";
import { useScrollRestore } from "../hooks/useScrollMemory";

const BREAKPOINTS = { default: 5, 1400: 4, 1100: 3, 900: 2, 640: 1 };

interface ListData { posts: PostSummary[]; page: number; total: number }

export default function Home() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navType = useNavigationType();
  const q = searchParams.get("q") || "";
  const uid = searchParams.get("uid") || "";

  const routeKey = `home:${q}:${uid}`;
  const cached = useRef(
    navType === "POP" ? loadListCache<ListData>(routeKey) : null
  ).current;

  const [posts, setPosts] = useState<PostSummary[]>(cached?.posts ?? []);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const favIdsRef = useRef<Set<string>>(new Set());
  const [page, setPage] = useState(cached?.page ?? 1);
  const [total, setTotal] = useState(cached?.total ?? 0);
  const [loading, setLoading] = useState(!cached);
  const skipFetchRef = useRef(!!cached);

  const loadingRef = useRef(false);
  const canLoadMoreRef = useRef(false);
  const routeKeyRef = useRef(routeKey);

  useEffect(() => { loadingRef.current = loading; }, [loading]);
  useEffect(() => { canLoadMoreRef.current = posts.length < total; }, [posts.length, total]);
  useEffect(() => { favIdsRef.current = favIds; }, [favIds]);

  useScrollRestore(posts.length > 0 || (!loading && total === 0));

  // Reset when query changes within same component instance
  useEffect(() => {
    if (routeKeyRef.current !== routeKey) {
      routeKeyRef.current = routeKey;
      skipFetchRef.current = false;
      setPosts([]);
      setPage(1);
      setTotal(0);
    }
  }, [routeKey]);

  // Save to in-memory cache
  useEffect(() => {
    if (posts.length > 0) saveListCache(routeKey, { posts, page, total });
  }, [posts, page, total, routeKey]);

  // Fetch posts
  useEffect(() => {
    if (skipFetchRef.current) { skipFetchRef.current = false; return; }
    let cancelled = false;
    setLoading(true);
    fetchPosts({ page, size: 90, q, uid })
      .then((data) => {
        if (cancelled) return;
        setPosts((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, q, uid]);

  // fetch favorite IDs
  useEffect(() => {
    fetchFavoriteIds().then((ids) => setFavIds(new Set(ids)));
  }, []);

  // Prefetch: trigger next page when ~2 viewports remain (~60 of 90 images)
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

  const toggleFav = useCallback((postUid: string, postId: string) => {
    const key = `${postUid}_${postId}`;
    const wasFav = favIdsRef.current.has(key);

    // Optimistic update: render first, sync server in background.
    setFavIds((prev) => {
      const next = new Set(prev);
      if (wasFav) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });

    const req = wasFav ? removeFavorite(postUid, postId) : addFavorite(postUid, postId);
    req.catch(() => {
      // Roll back only when request fails.
      setFavIds((prev) => {
        const next = new Set(prev);
        if (wasFav) {
          next.add(key);
        } else {
          next.delete(key);
        }
        return next;
      });
    });
  }, []);

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
      {q && <div className="text-lg font-semibold mb-4 pl-1 flex items-center gap-2.5">搜索: {q}</div>}
      {uid && <div className="text-lg font-semibold mb-4 pl-1 flex items-center gap-2.5">UID: {uid}</div>}

      <Masonry
        breakpointCols={BREAKPOINTS}
        className="masonry-grid"
        columnClassName="masonry-column"
      >
        {posts.map((post) => (
          <PostCard
            key={`${post.uid}_${post.id}`}
            post={post}
            isFav={favIds.has(`${post.uid}_${post.id}`)}
            onToggleFav={toggleFav}
            onDeleted={handleDeleted}
            onBlocked={handleBlocked}
          />
        ))}
      </Masonry>

      <div className="flex justify-center py-8 text-text-secondary text-sm">
        {loading && <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />}
        {!loading && posts.length >= total && posts.length > 0 && (
          <span>没有更多了</span>
        )}
        {!loading && posts.length === 0 && (
          <div className="text-center py-16 text-text-secondary">
            <p>暂无内容</p>
          </div>
        )}
      </div>
    </>
  );
}
