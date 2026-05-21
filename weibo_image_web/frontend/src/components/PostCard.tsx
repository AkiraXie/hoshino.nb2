import { memo, useState, useRef, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { PostSummary } from "../types";
import PostModal from "./PostModal";
import UserAvatar from "./UserAvatar";
import StaticImage from "./StaticImage";

const postArCache = new Map<string, string>();

interface PostCardProps {
  post: PostSummary;
  isFav: boolean;
  onToggleFav: (uid: string, id: string) => void;
  onDeleted?: (uid: string, id: string) => void;
  onBlocked?: (uid: string) => void;
  hideAuthor?: boolean;
}

function getAspectClass(w: number, h: number) {
  const r = w / h;
  if (r > 1.2) return "h-[260px]";
  if (r < 0.8) return "h-[480px]";
  return "h-[380px]";
}

const isMobile = () => window.matchMedia("(max-width: 600px)").matches;

function PostCard({ post, isFav, onToggleFav, onDeleted, onBlocked, hideAuthor }: PostCardProps) {
  const cacheKey = `${post.uid}_${post.id}`;
  const [imgH, setImgH] = useState<string>(() => postArCache.get(cacheKey) || "h-[380px]");
  const [loaded, setLoaded] = useState<boolean>(() => postArCache.has(cacheKey));
  const [showModal, setShowModal] = useState(false);
  const imgWrapRef = useRef<HTMLSpanElement>(null);
  const navigate = useNavigate();

  // Fallback: if img already complete when React mounts (lazy-load race), mark loaded
  useEffect(() => {
    if (loaded) return;
    const img = imgWrapRef.current?.querySelector?.('img');
    if (img && img.complete && img.naturalWidth > 0) {
      const resolved = getAspectClass(img.naturalWidth, img.naturalHeight);
      postArCache.set(cacheKey, resolved);
      setImgH(resolved);
      setLoaded(true);
    }
  }, [loaded, cacheKey]);

  const handleImgLoad = (e: React.SyntheticEvent<HTMLImageElement, Event>) => {
    const img = e.currentTarget;
    const resolved = getAspectClass(img.naturalWidth, img.naturalHeight);
    postArCache.set(cacheKey, resolved);
    setImgH(resolved);
    setLoaded(true);
  };

  return (
    <>
      <div
        className={`relative bg-transparent rounded-card border-none overflow-hidden mb-6 cursor-pointer
                    transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]
                    hover:-translate-y-1.5 hover:scale-[1.015] hover:shadow-card-hover`}
        data-post-key={`${post.uid}_${post.id}`}
        onClick={() => {
          if (isMobile()) {
            navigate(`/post/${post.uid}/${post.id}`);
          } else {
            setShowModal(true);
          }
        }}
      >
        {post.cover && (
          <span ref={imgWrapRef}>
            <StaticImage
              className={`post-card-img w-full block ${imgH} ${loaded ? "loaded" : ""}`}
              src={post.cover}
              alt=""
              loading="lazy"
              decoding="async"
              onLoad={handleImgLoad}
            />
          </span>
        )}

        {/* Hover overlay */}
        <div
          className="absolute inset-0 bg-gradient-to-b from-black/25 via-transparent to-black/70
                     opacity-0 group-hover:opacity-100 transition-opacity duration-[250ms] ease-[cubic-bezier(0.4,0,0.2,1)]
                     flex flex-col justify-between p-4 z-[5]"
          style={{ pointerEvents: showModal ? "none" : "auto" }}
        >
          {/* Fav button — top right */}
          <button
            className={`self-end bg-white/90 backdrop-blur-[8px] border border-border text-text cursor-pointer
                       w-9 h-9 flex items-center justify-center rounded-full shadow-[0_4px_12px_rgba(0,0,0,0.12)]
                       transition-all duration-200 ease-[cubic-bezier(0.175,0.885,0.32,1.275)]
                       hover:scale-[1.15] hover:rotate-[5deg] hover:bg-white
                       ${isFav ? "!bg-primary !border-primary text-white hover:!bg-primary-dark hover:!border-primary-dark" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggleFav(post.uid, post.id);
            }}
            title={isFav ? "取消收藏" : "加入收藏"}
          >
            {isFav ? (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
              </svg>
            )}
          </button>

          {/* Bottom row: author & meta */}
          <div className="flex items-center justify-between w-full">
            {!hideAuthor && (
              <Link
                to={`/uid/${post.uid}`}
                className="flex items-center gap-2 text-white no-underline text-[13px] font-semibold overflow-hidden text-ellipsis whitespace-nowrap hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                <img
                  className="rounded-full object-cover bg-[#eee] shrink-0"
                  src={`/media/${encodeURIComponent(post.uid)}/user_avatar.jpg`}
                  alt=""
                  width={24}
                  height={24}
                  onError={(e) => { e.currentTarget.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3Crect fill='%23eee' width='1' height='1'/%3E%3C/svg%3E"; e.currentTarget.onerror = null; }}
                />
                <span className="overflow-hidden text-ellipsis whitespace-nowrap max-w-[140px] max-md:max-w-[80px]">{post.nickname || post.uid}</span>
              </Link>
            )}
            <div className="flex gap-1.5 shrink-0">
              {post.image_count > 0 && (
                <span className="inline-flex items-center gap-1 bg-black/60 backdrop-blur-[8px] text-white px-2 py-1 text-[11px] font-bold rounded-xl border border-white/25" title="图片数量">
                  <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    <circle cx="8.5" cy="8.5" r="1.5"></circle>
                    <polyline points="21 15 16 10 5 21"></polyline>
                  </svg>
                  {post.image_count}
                </span>
              )}
              {post.video_count > 0 && (
                <span className="inline-flex items-center gap-1 bg-black/60 backdrop-blur-[8px] text-white px-2 py-1 text-[11px] font-bold rounded-xl border border-white/25" title="视频数量">
                  <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                    <line x1="7" y1="2" x2="7" y2="22"></line>
                    <line x1="17" y1="2" x2="17" y2="22"></line>
                    <line x1="2" y1="12" x2="22" y2="12"></line>
                    <line x1="2" y1="7" x2="7" y2="7"></line>
                    <line x1="2" y1="17" x2="7" y2="17"></line>
                    <line x1="17" y1="17" x2="22" y2="17"></line>
                    <line x1="17" y1="7" x2="22" y2="7"></line>
                  </svg>
                  {post.video_count}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {showModal && (
        <PostModal
          uid={post.uid}
          postId={post.id}
          isFav={isFav}
          onClose={() => setShowModal(false)}
          onToggleFav={onToggleFav}
          onDeleted={onDeleted}
          onBlocked={onBlocked}
        />
      )}
    </>
  );
}

export default memo(PostCard, (prev, next) => {
  return (
    prev.post === next.post &&
    prev.isFav === next.isFav &&
    prev.hideAuthor === next.hideAuthor
  );
});
