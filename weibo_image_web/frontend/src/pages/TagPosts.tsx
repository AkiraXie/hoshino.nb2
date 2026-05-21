import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigationType } from "react-router-dom";
import Masonry from "react-masonry-css";
import PostCard from "../components/PostCard";
import {
  fetchTagPosts,
  fetchFavoriteIds,
  addFavorite,
  removeFavorite,
} from "../api";
import type { PostSummary } from "../types";
import { saveListCache, loadListCache } from "../hooks/listCache";
import { useScrollRestore } from "../hooks/useScrollMemory";

const BREAKPOINTS = { default: 5, 1400: 4, 1100: 3, 900: 2, 640: 1 };

interface ListData { posts: PostSummary[]; page: number; total: number }

export default function TagPosts() {
  const { tag = "" } = useParams();
  const navType = useNavigationType();
  const cacheKey = `tag_${tag}`;

  const cached = useRef(
    navType === "POP" ? loadListCache<ListData>(cacheKey) : null
  ).current;

  const [posts, setPosts] = useState<PostSummary[]>(cached?.posts ?? []);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(cached?.page ?? 1);
  const [total, setTotal] = useState(cached?.total ?? 0);
  const [loading, setLoading] = useState(!cached);
  const skipFetchRef = useRef(!!cached);

  const loadingRef = useRef(false);
  const canLoadMoreRef = useRef(false);

  useEffect(() => { loadingRef.current = loading; }, [loading]);
  useEffect(() => { canLoadMoreRef.current = posts.length < total; }, [posts.length, total]);

  useScrollRestore(posts.length > 0 || (!loading && total === 0));

  useEffect(() => {
    if (posts.length > 0) saveListCache(cacheKey, { posts, page, total });
  }, [posts, page, total, cacheKey]);

  // fetch tag posts
  useEffect(() => {
    if (skipFetchRef.current) { skipFetchRef.current = false; return; }
    let cancelled = false;
    setLoading(true);
    fetchTagPosts(tag, { page, size: 90 })
      .then((data) => {
        if (cancelled) return;
        setPosts((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tag, page]);

  // fetch fav IDs
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
        setFavIds((prev) => {
          const s = new Set(prev);
          s.delete(key);
          return s;
        });
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
      <div className="text-lg font-semibold mb-4 pl-1 flex items-center gap-2.5">{decodeURIComponent(tag)}</div>
      <div className="text-sm text-text-secondary/50 mb-6">{total} 条微博</div>

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
            <p>该标签下暂无内容</p>
          </div>
        )}
      </div>
    </>
  );
}
