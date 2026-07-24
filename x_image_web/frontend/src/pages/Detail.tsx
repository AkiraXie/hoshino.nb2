import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { PostDetail } from "../types";
import { fetchPostDetail, mediaUrl, fetchFavoriteIds, addFavorite, removeFavorite } from "../api";
import ImageViewer from "../components/ImageViewer";

export default function Detail() {
  const { uid, id } = useParams<{ uid: string; id: string }>();
  const [post, setPost] = useState<PostDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [isFav, setIsFav] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  useEffect(() => {
    if (!uid || !id) return;
    setLoading(true);
    Promise.all([fetchPostDetail(uid, id), fetchFavoriteIds()])
      .then(([data, favIds]) => {
        setPost(data);
        setIsFav(favIds.includes(`${uid}_${id}`));
      })
      .catch(() => setPost(null))
      .finally(() => setLoading(false));
  }, [uid, id]);

  const toggleFav = async () => {
    if (!uid || !id) return;
    try {
      if (isFav) {
        await removeFavorite(uid, id);
        setIsFav(false);
      } else {
        await addFavorite(uid, id);
        setIsFav(true);
      }
    } catch {
      // ignore
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!post) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-text-muted">
        <p>推文未找到</p>
        <Link to="/" className="text-accent-light hover:text-accent mt-2">返回首页</Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <Link to={`/uid/${post.uid}`} className="text-text-secondary hover:text-accent-light no-underline text-sm mb-4 inline-block transition-colors">
        ← @{post.uid}
      </Link>

      <div className="bg-bg-card border border-border rounded-2xl p-6">
        {/* Author */}
        <div className="flex items-center gap-3 mb-4">
          <span className="w-12 h-12 rounded-full bg-frost flex items-center justify-center text-lg text-ice font-bold">
            {(post.nickname || post.uid)[0]?.toUpperCase()}
          </span>
          <div>
            <div className="font-semibold text-text-primary">{post.nickname || post.uid}</div>
            <div className="text-sm text-text-muted">
              @{post.uid} · {new Date(post.timestamp * 1000).toLocaleString("zh-CN")}
            </div>
          </div>
        </div>

        {/* Content */}
        <p className="text-text-primary leading-relaxed whitespace-pre-wrap mb-4">
          {post.content}
        </p>

        {/* Repost */}
        {post.repost && (
          <div className="border border-border rounded-xl p-4 mb-4 bg-bg-elevated/50">
            <div className="text-xs text-text-muted mb-1">转推 @{post.repost.nickname}</div>
            <p className="text-sm text-text-secondary whitespace-pre-wrap">{post.repost.content}</p>
          </div>
        )}

        {/* Images */}
        {post.images.length > 0 && (
          <div className={`grid gap-2 rounded-xl overflow-hidden mb-4 ${
            post.images.length === 1 ? "grid-cols-1" :
            post.images.length === 2 ? "grid-cols-2" :
            post.images.length === 3 ? "grid-cols-3" : "grid-cols-2"
          }`}>
            {post.images.map((img, i) => (
              <img
                key={i}
                src={mediaUrl(img)}
                alt=""
                className="w-full h-full object-cover cursor-pointer rounded-lg hover:opacity-90 transition-opacity"
                loading="lazy"
                onClick={() => setViewerIndex(i)}
              />
            ))}
          </div>
        )}

        {/* Videos */}
        {post.videos.length > 0 && (
          <div className="space-y-2 mb-4">
            {post.videos.map((vid, i) => (
              <video key={i} src={mediaUrl(vid)} controls className="w-full rounded-lg" preload="metadata" />
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-border">
          <div className="flex items-center gap-4">
            <button
              className={`flex items-center gap-1.5 text-sm cursor-pointer transition-colors ${
                isFav ? "text-accent-light" : "text-text-muted hover:text-accent-light"
              }`}
              onClick={toggleFav}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill={isFav ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
              {post.likes}
            </button>
          </div>
          {post.url && (
            <a href={post.url} target="_blank" rel="noopener noreferrer" className="text-sm text-accent-light hover:text-accent no-underline">
              查看原文 ↗
            </a>
          )}
        </div>
      </div>

      {viewerIndex !== null && (
        <ImageViewer
          images={post.images.map(mediaUrl)}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onNavigate={setViewerIndex}
        />
      )}
    </div>
  );
}
