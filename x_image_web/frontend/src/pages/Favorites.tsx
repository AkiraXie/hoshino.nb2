import { useEffect, useState, useCallback, useRef } from "react";
import Masonry from "react-masonry-css";
import type { PostSummary } from "../types";
import { fetchFavorites, fetchFavoriteIds, addFavorite, removeFavorite } from "../api";
import PostCard from "../components/PostCard";

const PAGE_SIZE = 30;

export default function Favorites() {
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
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    try {
      const data = await fetchFavorites(p, PAGE_SIZE);
      setPosts((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setPage(p);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
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

  const toggleFav = useCallback(async (uid: string, id: string) => {
    const key = `${uid}_${id}`;
    const isFav = favIds.has(key);
    try {
      if (isFav) {
        await removeFavorite(uid, id);
        setFavIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
        setPosts((prev) => prev.filter((p) => `${p.uid}_${p.id}` !== key));
        setTotal((t) => t - 1);
      } else {
        await addFavorite(uid, id);
        setFavIds((prev) => new Set(prev).add(key));
      }
    } catch {
      // ignore
    }
  }, [favIds]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-text-primary m-0">收藏</h1>
        <p className="text-sm text-text-muted mt-1">{total} 条收藏</p>
      </div>

      {posts.length > 0 ? (
        <Masonry
          breakpointCols={{ default: 5, 1400: 4, 1100: 3, 768: 2, 500: 1 }}
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
          <div className="flex flex-col items-center justify-center h-64 text-text-muted">
            <p className="text-lg">暂无收藏</p>
            <p className="text-sm mt-2">在推文中点击 ♥ 添加收藏</p>
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
