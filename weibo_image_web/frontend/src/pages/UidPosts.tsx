import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useNavigationType } from "react-router-dom";
import Masonry from "react-masonry-css";
import PostCard from "../components/PostCard";
import {
  fetchPosts,
  fetchFavoriteIds,
  fetchUidStats,
  addFavorite,
  removeFavorite,
  addToBlacklist,
} from "../api";
import type { PostSummary } from "../types";
import { saveListCache, loadListCache } from "../hooks/listCache";
import { useScrollRestore } from "../hooks/useScrollMemory";
import UserAvatar from "../components/UserAvatar";

const BREAKPOINTS = { default: 5, 1400: 4, 1100: 3, 900: 2, 640: 1 };

interface ListData { posts: PostSummary[]; page: number; total: number }

export default function UidPosts() {
  const { uid = "" } = useParams();
  const navigate = useNavigate();
  const navType = useNavigationType();

  const routeKey = `uid:${uid}`;
  const cached = useRef(
    navType === "POP" ? loadListCache<ListData>(routeKey) : null
  ).current;

  const [posts, setPosts] = useState<PostSummary[]>(cached?.posts ?? []);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(cached?.page ?? 1);
  const [total, setTotal] = useState(cached?.total ?? 0);
  const [loading, setLoading] = useState(!cached);
  const [uidStats, setUidStats] = useState<{ image_count: number; fav_count: number } | null>(null);
  const skipFetchRef = useRef(!!cached);

  const loadingRef = useRef(false);
  const canLoadMoreRef = useRef(false);

  useEffect(() => { loadingRef.current = loading; }, [loading]);
  useEffect(() => { canLoadMoreRef.current = posts.length < total; }, [posts.length, total]);

  useScrollRestore(posts.length > 0 || (!loading && total === 0));

  useEffect(() => {
    if (posts.length > 0) saveListCache(routeKey, { posts, page, total });
  }, [posts, page, total, routeKey]);

  useEffect(() => {
    if (skipFetchRef.current) { skipFetchRef.current = false; return; }
    if (!uid) return;
    let cancelled = false;
    setLoading(true);
    fetchPosts({ page, size: 90, uid })
      .then((data) => {
        if (cancelled) return;
        setPosts((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, uid]);

  useEffect(() => {
    fetchFavoriteIds().then((ids) => setFavIds(new Set(ids)));
    fetchUidStats().then((s) => { if (s[uid]) setUidStats(s[uid]); });
  }, [uid]);

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

  const handleBlock = useCallback(async () => {
    if (!window.confirm("确定拉黑该用户？拉黑后该用户的所有内容将不再显示。")) return;
    try {
      await addToBlacklist(uid);
      navigate("/");
    } catch {
      alert("拉黑失败");
    }
  }, [uid, navigate]);

  const handleBlocked = useCallback((_blockedUid: string) => {
    navigate("/");
  }, [navigate]);

  const nickname = posts.length > 0 ? posts[0].nickname : "";

  return (
    <>
      <button className="inline-flex items-center gap-1 bg-transparent border-none cursor-pointer text-sm text-text-secondary py-2 mb-3 hover:text-primary" onClick={() => navigate(-1)}>← 返回</button>
      <div className="flex items-start gap-5 mb-8">
        <UserAvatar uid={uid} size={72} />
        <div className="flex-1 min-w-0">
          <div className="text-xl font-bold text-text mb-1 truncate">{nickname || uid}</div>
          <div className="flex items-center gap-3 text-sm text-text-secondary/60 mb-2">
            <span>UID: {uid}</span>
            <a
              href={`https://weibo.com/u/${uid}`}
              className="text-primary/60 no-underline hover:text-primary transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              微博主页
            </a>
          </div>
          <div className="flex items-center gap-4 text-sm text-text-secondary/50 mb-3">
            <span>{total} 条微博</span>
            {uidStats && <span>{uidStats.image_count} 张图</span>}
            {uidStats && uidStats.fav_count > 0 && <span>{uidStats.fav_count} 收藏</span>}
          </div>
          <button
            onClick={handleBlock}
            className="text-xs font-medium text-text-secondary/30 hover:text-red-500 transition-colors bg-transparent border-none cursor-pointer px-0"
          >
            拉黑
          </button>
        </div>
      </div>

      <Masonry breakpointCols={BREAKPOINTS} className="masonry-grid" columnClassName="masonry-column">
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
        {!loading && posts.length >= total && posts.length > 0 && <span>没有更多了</span>}
        {!loading && posts.length === 0 && (
          <div className="text-center py-16 text-text-secondary"><p>该用户暂无内容</p></div>
        )}
      </div>
    </>
  );
}
