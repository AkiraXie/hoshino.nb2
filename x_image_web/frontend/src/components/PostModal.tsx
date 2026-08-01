import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import type { PostDetail } from "../types";
import { fetchPostDetail, mediaUrl } from "../api";
import ImageViewer from "./ImageViewer";

interface PostModalProps {
  uid: string;
  postId: string;
  isFav: boolean;
  onClose: () => void;
  onToggleFav: (uid: string, id: string) => void;
}

export default function PostModal({ uid, postId, isFav, onClose, onToggleFav }: PostModalProps) {
  const [post, setPost] = useState<PostDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPostDetail(uid, postId)
      .then((data) => { if (!cancelled) setPost(data); })
      .catch(() => { if (!cancelled) setPost(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [uid, postId]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") {
      if (viewerIndex !== null) setViewerIndex(null);
      else onClose();
    }
  }, [viewerIndex, onClose]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  const allMedia = post ? [...post.images, ...post.videos] : [];

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

      {/* Modal content */}
      <div
        className="relative bg-bg-secondary border border-border rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : post ? (
          <div className="p-6">
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-full bg-frost flex items-center justify-center text-sm text-ice font-bold">
                  {(post.nickname || post.uid)[0]?.toUpperCase()}
                </span>
                <div>
                  <Link
                    to={`/uid/${post.uid}`}
                    className="text-text-primary font-semibold no-underline hover:text-accent-light transition-colors"
                    onClick={onClose}
                  >
                    {post.nickname || post.uid}
                  </Link>
                  <div className="text-xs text-text-muted">
                    @{post.uid} · {new Date(post.timestamp * 1000).toLocaleString("zh-CN")}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  className={`w-9 h-9 rounded-full flex items-center justify-center border cursor-pointer transition-all hover:scale-110
                    ${isFav ? "bg-accent border-accent text-white" : "bg-bg-card border-border text-text-secondary hover:text-accent-light"}`}
                  onClick={() => onToggleFav(post.uid, post.id)}
                >
                  {isFav ? (
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                      <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                    </svg>
                  )}
                </button>
                <button
                  className="w-9 h-9 rounded-full flex items-center justify-center bg-bg-card border border-border text-text-secondary cursor-pointer hover:text-text-primary transition-colors"
                  onClick={onClose}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Content */}
            <p className="text-text-primary leading-relaxed whitespace-pre-wrap mb-4">
              {post.content}
            </p>

            {/* Repost */}
            {post.repost && (
              <div className="border border-border rounded-xl p-4 mb-4 bg-bg-card/50">
                <div className="text-xs text-text-muted mb-1">
                  转推 @{post.repost.nickname}
                </div>
                <p className="text-sm text-text-secondary whitespace-pre-wrap">
                  {post.repost.content}
                </p>
              </div>
            )}

            {/* Media grid */}
            {allMedia.length > 0 && (
              <div className={`grid gap-2 rounded-xl overflow-hidden ${
                allMedia.length === 1 ? "grid-cols-1" :
                allMedia.length === 2 ? "grid-cols-2" :
                allMedia.length === 3 ? "grid-cols-3" : "grid-cols-2"
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
                {post.videos.map((vid, i) => (
                  <video
                    key={`v${i}`}
                    src={mediaUrl(vid)}
                    controls
                    className="w-full rounded-lg"
                    preload="metadata"
                  />
                ))}
              </div>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
              <span className="text-sm text-text-muted flex items-center gap-1">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" className="text-accent-light/70">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
                </svg>
                {post.likes}
              </span>
              {post.url && (
                <a
                  href={post.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-accent-light hover:text-accent no-underline transition-colors"
                >
                  查看原文 ↗
                </a>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 text-text-muted">
            加载失败
          </div>
        )}
      </div>

      {/* Full-screen image viewer */}
      {viewerIndex !== null && post && (
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
