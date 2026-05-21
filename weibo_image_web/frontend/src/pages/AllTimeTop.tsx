import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useNavigationType } from "react-router-dom";
import { fetchTopUids, fetchFavoriteIds, addFavorite, removeFavorite } from "../api";
import type { TopUidInfo } from "../types";
import PostCard from "../components/PostCard";
import UserAvatar from "../components/UserAvatar";
import { saveListCache, loadListCache } from "../hooks/listCache";
import { useScrollRestore } from "../hooks/useScrollMemory";

export default function AllTimeTop() {
  const navType = useNavigationType();
  const cached = useRef(
    navType === "POP" ? loadListCache<{ topUids: TopUidInfo[] }>("allTimeTop") : null
  ).current;

  const [topUids, setTopUids] = useState<TopUidInfo[]>(cached?.topUids ?? []);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(!cached);
  const skipFetchRef = useRef(!!cached);

  useScrollRestore(topUids.length > 0 || (!loading));

  useEffect(() => {
    if (topUids.length > 0) saveListCache("allTimeTop", { topUids });
  }, [topUids]);

  useEffect(() => {
    if (skipFetchRef.current) { skipFetchRef.current = false; return; }
    setLoading(true);
    fetchTopUids({ limit: 11, preview: 4 })
      .then(setTopUids)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchFavoriteIds().then((ids) => setFavIds(new Set(ids)));
  }, []);

  const toggleFav = useCallback(
    async (uid: string, id: string) => {
      const key = `${uid}_${id}`;
      if (favIds.has(key)) {
        await removeFavorite(uid, id);
        setFavIds((prev) => { const s = new Set(prev); s.delete(key); return s; });
      } else {
        await addFavorite(uid, id);
        setFavIds((prev) => new Set(prev).add(key));
      }
    },
    [favIds]
  );

  const handleDeleted = useCallback((delUid: string, delId: string) => {
    setTopUids((prev) => prev.map((item) => ({
      ...item,
      posts: item.posts.filter((p) => !(p.uid === delUid && p.id === delId)),
    })));
  }, []);

  const handleBlocked = useCallback((blockedUid: string) => {
    setTopUids((prev) => prev.filter((item) => item.uid !== blockedUid));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />
      </div>
    );
  }

  if (topUids.length === 0) {
    return (
      <div className="text-center py-16 text-text-secondary/60">
        <p className="text-sm">暂无数据</p>
      </div>
    );
  }

  const top1 = topUids[0];
  const rest = topUids.slice(1);

  return (
    <>
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-text">全站博主排行</h2>
        <p className="text-sm text-text-secondary/50 mt-1">按微博数量排序</p>
      </div>

      {/* #1 Featured — open layout, accent border-left */}
      <div className="mb-10 pl-5 border-l-[3px] border-primary">
        <div className="flex items-center gap-3 mb-5">
          <span className="text-xl font-bold text-primary">#1</span>
          <UserAvatar uid={top1.uid} size={36} />
          <Link
            to={`/uid/${top1.uid}`}
            className="text-lg font-semibold text-text no-underline hover:text-primary transition-colors truncate"
          >
            {top1.nickname || top1.uid}
          </Link>
          <span className="ml-auto text-sm text-text-secondary/50 font-medium whitespace-nowrap">
            {top1.count} 条
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {top1.posts.map((post) => (
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
        </div>
      </div>

      {/* #2-#11 — grid of compact items, no card boxes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {rest.map((item, i) => (
          <div key={item.uid}>
            <div className="flex items-center gap-2.5 mb-3">
              <span className="text-sm font-bold text-text-secondary/40 min-w-[20px]">
                #{i + 2}
              </span>
              <UserAvatar uid={item.uid} size={24} />
              <Link
                to={`/uid/${item.uid}`}
                className="text-sm font-semibold text-text no-underline hover:text-primary transition-colors truncate"
              >
                {item.nickname || item.uid}
              </Link>
              <span className="ml-auto text-xs text-text-secondary/40 font-medium whitespace-nowrap">
                {item.count} 条
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {item.posts.map((post) => (
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
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
