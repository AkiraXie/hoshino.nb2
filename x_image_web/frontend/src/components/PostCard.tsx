import { memo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { PostSummary } from "../types";
import { mediaUrl } from "../api";
import PostModal from "./PostModal";

interface PostCardProps {
  post: PostSummary;
  isFav: boolean;
  onToggleFav: (uid: string, id: string) => void;
}

const isMobile = () => window.matchMedia("(max-width: 600px)").matches;

function PostCard({ post, isFav, onToggleFav }: PostCardProps) {
  const [loaded, setLoaded] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const navigate = useNavigate();

  const coverSrc = post.cover ? mediaUrl(post.cover) : null;

  return (
    <>
      <div
        className="group relative bg-bg-card rounded-xl border border-border overflow-hidden mb-4 cursor-pointer
                   transition-all duration-300 ease-out
                   hover:-translate-y-1 hover:border-accent/40 hover:shadow-[0_8px_32px_rgba(59,130,246,0.12)]"
        onClick={() => {
          if (isMobile()) {
            navigate(`/post/${post.uid}/${post.id}`);
          } else {
            setShowModal(true);
          }
        }}
      >
        {coverSrc && (
          <div className="relative overflow-hidden">
            {!loaded && <div className="absolute inset-0 img-loading" />}
            <img
              className={`w-full block object-cover img-fade ${loaded ? "loaded" : ""}`}
              src={coverSrc}
              alt=""
              loading="lazy"
              decoding="async"
              onLoad={() => setLoaded(true)}
            />
          </div>
        )}

        {/* Content preview */}
        <div className="p-3">
          <p className="text-sm text-text-primary line-clamp-3 leading-relaxed mb-2">
            {post.content || "(无文字内容)"}
          </p>

          {/* Meta row */}
          <div className="flex items-center justify-between">
            <Link
              to={`/uid/${post.uid}`}
              className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-accent-light no-underline transition-colors"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="w-5 h-5 rounded-full bg-frost flex items-center justify-center text-[10px] text-ice font-bold shrink-0">
                {(post.nickname || post.uid)[0]?.toUpperCase()}
              </span>
              <span className="truncate max-w-[100px]">{post.nickname || post.uid}</span>
            </Link>

            <div className="flex items-center gap-2">
              {post.likes > 0 && (
                <span className="text-[11px] text-text-muted flex items-center gap-0.5">
                  <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" className="text-accent-light/70">
                    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
                  </svg>
                  {post.likes > 999 ? `${(post.likes / 1000).toFixed(1)}k` : post.likes}
                </span>
              )}
              {post.image_count > 1 && (
                <span className="text-[11px] text-text-muted flex items-center gap-0.5">
                  <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                  </svg>
                  {post.image_count}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Hover overlay: fav button */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
          <button
            className={`w-8 h-8 rounded-full flex items-center justify-center backdrop-blur-md border cursor-pointer
                       transition-all duration-200 hover:scale-110
                       ${isFav
                         ? "bg-accent/90 border-accent text-white"
                         : "bg-bg-primary/70 border-border text-text-secondary hover:text-accent-light hover:border-accent/50"}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggleFav(post.uid, post.id);
            }}
            title={isFav ? "取消收藏" : "加入收藏"}
          >
            {isFav ? (
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
            )}
          </button>
        </div>

        {/* Repost indicator */}
        {post.repost && (
          <div className="absolute top-2 left-2 bg-frost/80 backdrop-blur-sm text-ice text-[10px] px-2 py-0.5 rounded-full border border-accent/20">
            转推
          </div>
        )}
      </div>

      {showModal && (
        <PostModal
          uid={post.uid}
          postId={post.id}
          isFav={isFav}
          onClose={() => setShowModal(false)}
          onToggleFav={onToggleFav}
        />
      )}
    </>
  );
}

export default memo(PostCard, (prev, next) => {
  return prev.post === next.post && prev.isFav === next.isFav;
});
