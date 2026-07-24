import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import Masonry from "react-masonry-css";
import type { PostSummary } from "../types";
import { fetchPosts, fetchFavoriteIds, addFavorite, removeFavorite } from "../api";
import PostCard from "../components/PostCard";

const PAGE_SIZE = 30;

export default function UidPosts() {
  const { uid } = useParams<{ uid: string }>();
  const [posts, setPosts] = useState<PostSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const loadingRef = useRef(false);

  useEffect(() => {
    fetchFavoriteIds()
      .then((ids) => setFavIds(new Set(ids)))
      .catch(() => {});
  }, []);

  const loadPosts = useCallback(async (p: number, append: boolean) => {
    if (!uid || loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    try {
      const data = await fetchPosts({ page: p, size: PAGE_SIZE, uid });
      setPosts((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setPage(p);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, [uid]);

  useEffect(() => {
    setPosts([]);
    loadPosts(1, false);
  }, [loadPosts]);

  useEffect(() => {
    const handleScroll = () => {
      if (loadingRef.current) return;
      if (posts.length >= total) return;
      const scrollBottom = window.innerHeight + window.scrollY;
      if (scrollBottom >= document.body.offsetHeight - 600) {
        loadPosts(page + 1, true);
      }
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [posts.length, total, page, loadPosts]);

  const toggleFav = useCallback(async (uid_: string, id: string) => {
    const key = `${uid_}_${id}`;
    const isFav = favIds.has(key);
    try {
      if (isFav) {
        await removeFavorite(uid_, id);
        setFavIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
      } else {
        await addFavorite(uid_, id);
        setFavIds((prev) => new Set(prev).add(key));
      }
    } catch {
      // ignore
    }
  }, [favIds]);

  const nickname = posts[0]?.nickname || uid || "";

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to="/uids" className="text-text-secondary hover:text-accent-light no-underline transition-colors">
          ← 返回
        </Link>
        <span className="w-10 h-10 rounded-full bg-frost flex items-center justify-center text-sm text-ice font-bold">
          {nickname[0]?.toUpperCase()}
        </span>
        <div>
          <h1 className="text-lg font-bold text-text-primary m-0">{nickname}</h1>
          <p className="text-sm text-text-muted">@{uid} · {total} 条推文</p>
        </div>
      </div>

      {posts.length > 0 ? (
        <Masonry
          breakpointCols={{ default: 4, 1100: 3, 768: 2, 500: 1 }}
          className="masonry-grid"
          columnClassName="masonry-column"
        >
          {posts.map((post) => (
            <PostCard
              key={`${post.uid}_${post.id}`}
              post={post}
              isFav={favIds.has(`${post.uid}_${post.id}`)}
              onToggleFav={toggleFav}
            />
          ))}
        </Masonry>
      ) : (
        !loading && (
          <div className="flex items-center justify-center h-64 text-text-muted">
            暂无推文
          </div>
        )
      )}

      {loading && (
        <div className="flex justify-center py-8">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      )}
    </div>
  );
}
