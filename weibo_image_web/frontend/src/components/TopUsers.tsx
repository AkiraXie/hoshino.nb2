import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { fetchTopUids, fetchFavoriteIds, addFavorite, removeFavorite } from "../api";
import type { TopUidInfo } from "../types";
import PostCard from "./PostCard";

interface TopUsersProps {
  date?: string;
}

export default function TopUsers({ date }: TopUsersProps) {
  const [topUids, setTopUids] = useState<TopUidInfo[]>([]);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchTopUids({ limit: 5, preview: 4, date })
      .then(setTopUids)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [date]);

  useEffect(() => {
    fetchFavoriteIds().then((ids) => setFavIds(new Set(ids)));
  }, []);

  const toggleFav = async (uid: string, id: string) => {
    const key = `${uid}_${id}`;
    if (favIds.has(key)) {
      await removeFavorite(uid, id);
      setFavIds((prev) => { const s = new Set(prev); s.delete(key); return s; });
    } else {
      await addFavorite(uid, id);
      setFavIds((prev) => new Set(prev).add(key));
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-8 text-text-secondary text-sm">
        <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />
      </div>
    );
  }

  if (topUids.length === 0) {
    return (
      <div className="text-center py-16 text-text-secondary">
        <p>暂无数据</p>
      </div>
    );
  }

  const top1 = topUids[0];
  const rest = topUids.slice(1);

  const avatar = (uid: string, size: number) => (
    <img
      className="rounded-full object-cover bg-[#eee] shrink-0"
      src={`/media/${encodeURIComponent(uid)}/user_avatar.jpg`}
      alt=""
      width={size}
      height={size}
      onError={(e) => { e.currentTarget.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3Crect fill='%23eee' width='1' height='1'/%3E%3C/svg%3E"; e.currentTarget.onerror = null; }}
    />
  );

  return (
    <div className="flex flex-col gap-3">
      {/* #1 Featured */}
      <div className="bg-surface rounded-card border-[2.5px] border-primary p-4 shadow-elevated"
           style={{ background: "linear-gradient(145deg, #ffffff 0%, rgba(255,36,66,0.04) 100%)" }}>
        <div className="flex items-center gap-2 mb-2 pb-1.5 border-b border-border">
          <span className="text-xl font-bold text-primary min-w-[28px]">#1</span>
          {avatar(top1.uid, 32)}
          <Link to={`/uid/${top1.uid}`} className="text-base font-semibold text-text no-underline hover:text-primary transition-colors">
            {top1.nickname || top1.uid}
          </Link>
          <span className="ml-auto text-xs text-text-secondary">{top1.count} 条微博</span>
        </div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2 max-md:grid-cols-2">
          {top1.posts.map((post) => (
            <PostCard
              key={`${post.uid}_${post.id}`}
              post={post}
              isFav={favIds.has(`${post.uid}_${post.id}`)}
              onToggleFav={toggleFav}
              hideAuthor
            />
          ))}
        </div>
      </div>

      {/* #2-#5 in 2x2 grid */}
      {rest.length > 0 && (
        <div className="grid grid-cols-2 gap-2.5 max-md:grid-cols-1">
          {rest.map((item, i) => (
            <div key={item.uid} className="bg-surface rounded-card border border-border p-2 shadow-card">
              <div className="flex items-center gap-2 mb-2 pb-1.5 border-b border-border">
                <span className="text-base font-bold text-primary min-w-[28px]">#{i + 2}</span>
                {avatar(item.uid, 24)}
                <Link to={`/uid/${item.uid}`} className="text-sm font-semibold text-text no-underline hover:text-primary transition-colors">
                  {item.nickname || item.uid}
                </Link>
                <span className="ml-auto text-xs text-text-secondary">{item.count} 条微博</span>
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2 max-md:grid-cols-2 max-sm:grid-cols-1">
                {item.posts.map((post) => (
                  <PostCard
                    key={`${post.uid}_${post.id}`}
                    post={post}
                    isFav={favIds.has(`${post.uid}_${post.id}`)}
                    onToggleFav={toggleFav}
                    hideAuthor
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
