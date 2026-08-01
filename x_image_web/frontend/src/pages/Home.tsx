import { useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import Masonry from "react-masonry-css";
import type { PostSummary } from "../types";
import { fetchPosts, fetchFavoriteIds, addFavorite, removeFavorite } from "../api";
import PostCard from "../components/PostCard";

const PAGE_SIZE = 30;

export default function Home() {
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q") || "";

  const [posts, setPosts] = useState<PostSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const loadingRef = useRef(false);

  // Load favorites
  useEffect(() => {
    fetchFavoriteIds()
      .then((ids) => setFavIds(new Set(ids)))
      .catch(() => {});
  }, []);

  // Load posts
  const loadPosts = useCallback(async (p: number, append: boolean) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    try {
      const data = await fetchPosts({ page: p, size: PAGE_SIZE, q: query || undefined });
      setPosts((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setPage(p);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, [query]);

  useEffect(() => {
    setPosts([]);
    loadPosts(1, false);
  }, [loadPosts]);

  // Infinite scroll
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
      } else {
        await addFavorite(uid, id);
        setFavIds((prev) => new Set(prev).add(key));
      }
    } catch {
      // ignore
    }
  }, [favIds]);

  const breakpointCols = {
    default: 5,
    1400: 4,
    1100: 3,
    768: 2,
    500: 1,
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-text-primary m-0">
            {query ? `搜索: "${query}"` : "最新推文"}
          </h1>
          <p className="text-sm text-text-muted mt-1">{total} 条推文</p>
        </div>
      </div>

      {/* Masonry grid */}
      {posts.length > 0 ? (
        <Masonry
          breakpointCols={breakpointCols}
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
            <p className="text-lg">暂无推文数据</p>
            <p className="text-sm mt-2">请确认 X 插件已运行并有已发送的推文</p>
          </div>
        )
      )}

      {/* Loading indicator */}
      {loading && (
        <div className="flex justify-center py-8">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      )}
    </div>
  );
}
