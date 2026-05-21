import { useState, useEffect, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import type { PostDetail as PostDetailType } from "../types";
import {
  fetchPost,
  fetchPostTags,
  fetchTags,
  addTag,
  removeTag,
  addFavorite,
  removeFavorite,
  deletePost,
  addToBlacklist,
} from "../api";
import UserAvatar from "./UserAvatar";

interface PostModalProps {
  uid: string;
  postId: string;
  isFav: boolean;
  onClose: () => void;
  onToggleFav: (uid: string, id: string) => void;
  onDeleted?: (uid: string, id: string) => void;
  onBlocked?: (uid: string) => void;
}

export default function PostModal({
  uid,
  postId,
  isFav,
  onClose,
  onToggleFav,
  onDeleted,
  onBlocked,
}: PostModalProps) {
  const [post, setPost] = useState<PostDetailType | null>(null);
  const [imgIndex, setImgIndex] = useState(0);
  const [postTags, setPostTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [allTags, setAllTags] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [showAddInput, setShowAddInput] = useState(false);
  const tagFormRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchPost(uid, postId).then(setPost).catch(() => setPost(null));
    fetchPostTags(uid, postId).then(setPostTags);
    fetchTags().then((tags) => setAllTags(tags.map((t) => t.tag)));
  }, [uid, postId]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (!post) return;
      const totalMedia = post.images.length + post.videos.length + (post.images.length === 0 && post.screenshot ? 1 : 0);
      if (e.key === "ArrowLeft" && imgIndex > 0) setImgIndex((i) => i - 1);
      if (e.key === "ArrowRight" && imgIndex < totalMedia - 1)
        setImgIndex((i) => i + 1);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, post, imgIndex]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (tagFormRef.current && !tagFormRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleToggleFav = useCallback(() => {
    onToggleFav(uid, postId);
  }, [uid, postId, onToggleFav]);

  const handleDelete = useCallback(async () => {
    if (!window.confirm("确定删除这条微博？删除后会移入回收站。")) return;
    try {
      await deletePost(uid, postId);
      onDeleted?.(uid, postId);
      onClose();
    } catch {
      alert("删除失败");
    }
  }, [uid, postId, onClose, onDeleted]);

  const handleBlock = useCallback(async () => {
    if (!window.confirm("确定拉黑该用户？拉黑后该用户的所有内容将不再显示。")) return;
    try {
      await addToBlacklist(uid);
      onBlocked?.(uid);
      onClose();
    } catch {
      alert("拉黑失败");
    }
  }, [uid, onClose, onBlocked]);

  const handleAddTag = useCallback(async () => {
    const t = tagInput.trim();
    if (!t) return;
    try {
      await addTag(uid, postId, t);
      setPostTags((prev) => (prev.includes(t) ? prev : [...prev, t]));
      if (!allTags.includes(t)) setAllTags((prev) => [...prev, t]);
      setTagInput("");
      setShowSuggestions(false);
      setShowAddInput(false);
    } catch {
      alert("添加标签失败");
    }
  }, [uid, postId, tagInput, allTags]);

  const handleSelectSuggestion = useCallback(
    async (tag: string) => {
      if (postTags.includes(tag)) return;
      try {
        await addTag(uid, postId, tag);
        setPostTags((prev) => (prev.includes(tag) ? prev : [...prev, tag]));
        setTagInput("");
        setShowSuggestions(false);
        setShowAddInput(false);
      } catch {
        alert("添加标签失败");
      }
    },
    [uid, postId, postTags]
  );

  const handleToggleSystemTag = useCallback(
    async (tag: string) => {
      if (postTags.includes(tag)) {
        try {
          await removeTag(tag, uid, postId);
          setPostTags((prev) => prev.filter((t) => t !== tag));
        } catch {
          alert("移除标签失败");
        }
      } else {
        try {
          await addTag(uid, postId, tag);
          setPostTags((prev) => [...prev, tag]);
        } catch {
          alert("添加标签失败");
        }
      }
    },
    [uid, postId, postTags]
  );

  const handleRemoveTag = useCallback(
    async (tag: string) => {
      try {
        await removeTag(tag, uid, postId);
        setPostTags((prev) => prev.filter((t) => t !== tag));
      } catch {
        alert("移除标签失败");
      }
    },
    [uid, postId]
  );

  if (!post) {
    return (
      <div className="fixed inset-0 z-[200] bg-black/75 flex items-center justify-center" style={{ animation: "modalFadeIn 0.2s ease" }} onClick={onClose}>
        <div className="flex items-center justify-center">
          <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />
        </div>
      </div>
    );
  }

  const timestamp = post.timestamp
    ? new Date(post.timestamp * 1000).toLocaleString("zh-CN")
    : "";

  const media: { type: "image" | "video"; src: string }[] = [];
  if (post.images.length > 0) {
    for (const src of post.images) media.push({ type: "image", src });
  } else if (post.screenshot) {
    media.push({ type: "image", src: post.screenshot });
  }
  for (const src of post.videos) media.push({ type: "video", src });

  const current = media[imgIndex];

  return (
    <div className="fixed inset-0 z-[200] bg-black/75 flex items-center justify-center" style={{ animation: "modalFadeIn 0.2s ease" }} onClick={onClose}>
      <div
        className="relative flex w-[90vw] max-w-[1100px] h-[80vh] max-h-[720px] bg-surface rounded-card
                   border border-border overflow-hidden shadow-[0_24px_60px_rgba(28,27,24,0.15),0_4px_16px_rgba(28,27,24,0.05)]
                   max-md:flex-col max-md:w-[95vw] max-md:h-[90vh] max-md:max-h-none"
        style={{ animation: "modalSlideIn 0.3s cubic-bezier(0.16,1,0.3,1)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          className="absolute top-4 right-4 z-10 w-[38px] h-[38px] rounded-full border border-border bg-surface text-text
                     flex items-center justify-center cursor-pointer shadow-card transition-all duration-200
                     hover:bg-primary hover:text-white hover:border-primary hover:rotate-90 hover:scale-110 hover:shadow-[0_4px_12px_rgba(255,36,66,0.2)]"
          onClick={onClose}
          title="关闭 (Esc)"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        {/* Left: media carousel */}
        <div className="flex-1 min-w-0 bg-[#0d0d0d] flex items-center justify-center relative overflow-hidden max-md:flex-none max-md:h-1/2">
          {current && current.type === "image" && (
            <div className="ambient-backdrop" style={{ backgroundImage: `url(${current.src})` }} />
          )}

          {/* Top-right corner actions */}
          <div className="absolute top-4 right-4 z-10 flex gap-2">
            <button
              className={`w-10 h-10 flex items-center justify-center rounded-full border transition-all duration-200
                         bg-white/95 backdrop-blur-[8px] shadow-[0_4px_12px_rgba(0,0,0,0.15)]
                         hover:bg-white hover:scale-[1.18] hover:text-text
                         ${isFav ? "!bg-primary !border-primary text-white hover:!bg-primary-dark hover:!border-primary-dark" : "border-border text-text"}`}
              onClick={handleToggleFav}
              title={isFav ? "取消收藏" : "加入收藏"}
            >
              {isFav ? (
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
                </svg>
              )}
            </button>

            <button
              className="w-10 h-10 flex items-center justify-center rounded-full bg-white/95 backdrop-blur-[8px] border border-border
                         shadow-[0_4px_12px_rgba(0,0,0,0.15)] text-text hover:bg-blue-50 hover:border-blue-400 hover:text-blue-500
                         transition-all duration-200 hover:scale-[1.18]"
              onClick={() => window.open(post.url, "_blank")}
              title="查看原微博"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
            </button>
          </div>

          {media.length > 0 ? (
            <>
              {current.type === "image" ? (
                <img
                  className="max-w-full max-h-full object-contain select-none z-[2] relative"
                  style={{ filter: "drop-shadow(0 15px 30px rgba(0,0,0,0.45))" }}
                  src={current.src}
                  alt=""
                />
              ) : (
                <video
                  className="max-w-full max-h-full object-contain z-[2] relative"
                  src={current.src}
                  controls
                  preload="metadata"
                />
              )}
              {media.length > 1 && (
                <>
                  {imgIndex > 0 && (
                    <button
                      className="absolute top-1/2 -translate-y-1/2 left-4 w-[44px] h-[44px] rounded-full border border-border
                                 bg-surface text-text z-[5] cursor-pointer flex items-center justify-center
                                 transition-all duration-150 hover:bg-text hover:text-white hover:scale-110"
                      onClick={() => setImgIndex((i) => i - 1)}
                    >
                      <svg viewBox="0 0 24 24" width="20" height="24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="15 18 9 12 15 6"></polyline>
                      </svg>
                    </button>
                  )}
                  {imgIndex < media.length - 1 && (
                    <button
                      className="absolute top-1/2 -translate-y-1/2 right-4 w-[44px] h-[44px] rounded-full border border-border
                                 bg-surface text-text z-[5] cursor-pointer flex items-center justify-center
                                 transition-all duration-150 hover:bg-text hover:text-white hover:scale-110"
                      onClick={() => setImgIndex((i) => i + 1)}
                    >
                      <svg viewBox="0 0 24 24" width="20" height="24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                      </svg>
                    </button>
                  )}
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-white/90 border border-border text-black px-4 py-1 rounded-full text-xs font-bold z-[5]">
                    {imgIndex + 1} / {media.length}
                  </div>
                </>
              )}
            </>
          ) : (
            <div className="text-[#666] text-base z-[2] relative">暂无图片</div>
          )}
        </div>

        {/* Right: info panel */}
        <div className="w-[380px] shrink-0 flex flex-col p-8 overflow-y-auto border-l-2 border-border bg-surface max-md:w-full max-md:flex-1 max-md:min-h-0 max-md:p-4 max-md:border-l-0 max-md:border-t">
          {/* Author */}
          <div className="flex items-center gap-3 mb-5">
            <img
              className="rounded-full object-cover bg-[#eee] shrink-0"
              src={`/media/${encodeURIComponent(post.uid)}/user_avatar.jpg`}
              alt=""
              width={36}
              height={36}
              onError={(e) => { e.currentTarget.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3Crect fill='%23eee' width='1' height='1'/%3E%3C/svg%3E"; e.currentTarget.onerror = null; }}
            />
            <Link
              to={`/uid/${post.uid}`}
              className="text-lg font-bold text-text no-underline hover:underline hover:text-primary transition-colors"
              onClick={onClose}
            >
              {post.nickname || `UID: ${post.uid}`}
            </Link>
          </div>

          {/* Content */}
          {post.content && (
            <div className="text-sm leading-[1.7] text-text whitespace-pre-wrap break-all mb-3">{post.content}</div>
          )}

          {/* Time */}
          {timestamp && (
            <div className="text-xs text-text-secondary mb-4">{timestamp}</div>
          )}

          {/* Tags — larger, longer pill tags */}
          <div className="flex flex-wrap items-center gap-2 pt-4 mt-3 border-t border-border-light">
            {allTags.map((tag) => {
              const active = postTags.includes(tag);
              return (
                <button
                  key={tag}
                  onClick={() => {
                    if (active) {
                      handleRemoveTag(tag);
                    } else {
                      handleToggleSystemTag(tag);
                    }
                  }}
                  className={`inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-semibold transition-all duration-150 border cursor-pointer ${
                    active
                      ? "bg-primary border-primary text-white hover:bg-primary-dark"
                      : "bg-white border-border text-text-secondary hover:border-primary hover:text-primary"
                  }`}
                >
                  {active ? (
                    <>
                      {tag}
                      <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </>
                  ) : (
                    tag
                  )}
                </button>
              );
            })}

            {/* Add tag */}
            <div ref={tagFormRef} className="inline-flex items-center">
              {!showAddInput ? (
                <button
                  onClick={() => setShowAddInput(true)}
                  className="w-8 h-8 flex items-center justify-center rounded-full border border-dashed border-border bg-transparent text-text-secondary hover:border-primary hover:text-primary transition-all duration-200"
                  title="添加新标签"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </button>
              ) : (
                <form
                  className="flex items-center gap-1 bg-white border border-border rounded-full px-2 py-1 focus-within:border-primary transition-all"
                  onSubmit={(e) => { e.preventDefault(); handleAddTag(); }}
                >
                  <input
                    type="text"
                    autoFocus
                    className="w-24 border-none outline-none bg-transparent text-xs font-medium px-1"
                    placeholder="新标签"
                    value={tagInput}
                    onChange={(e) => { setTagInput(e.target.value); setShowSuggestions(true); }}
                    onFocus={() => setShowSuggestions(true)}
                  />
                  <button type="submit" className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-green-100 hover:text-green-600 transition-colors text-text-secondary" title="确定">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                  </button>
                  <button
                    type="button"
                    className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-red-100 hover:text-red-500 transition-colors text-text-secondary"
                    title="取消"
                    onClick={() => { setShowAddInput(false); setTagInput(""); }}
                  >
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>

                  {showSuggestions && (() => {
                    const needle = tagInput.trim().toLowerCase();
                    const suggestions = allTags.filter(
                      (t) => !postTags.includes(t) && (needle === "" || t.toLowerCase().includes(needle))
                    );
                    if (suggestions.length === 0) return null;
                    return (
                      <div className="absolute top-full left-0 mt-1 bg-white border border-border rounded-xl shadow-xl z-[100] p-1 flex flex-row gap-0.5 max-w-[240px] overflow-x-auto">
                        {suggestions.map((s) => (
                          <button
                            key={s}
                            className="shrink-0 px-3 py-1.5 rounded-full text-xs font-medium hover:bg-primary-light hover:text-primary transition-colors cursor-pointer border-none bg-surface-hover"
                            onMouseDown={(e) => {
                              e.preventDefault();
                              handleSelectSuggestion(s);
                            }}
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </form>
              )}
            </div>
          </div>

          {/* Bottom area */}
          <div className="flex flex-col gap-3 mt-auto border-t border-dashed border-border pt-4">
            <Link
              to={`/post/${post.uid}/${post.id}`}
              className="block text-center py-2.5 border border-border rounded-full text-text no-underline text-[13px] font-bold uppercase tracking-[0.05em] transition-all hover:border-text hover:bg-text hover:text-white"
              onClick={onClose}
            >
              查看详情 →
            </Link>

            <div className="flex justify-center gap-3">
              <button
                className="inline-flex items-center gap-1.5 h-[30px] px-3 rounded-full border border-border bg-surface text-[11px] font-extrabold cursor-pointer transition-all hover:bg-red-50 hover:border-red-500 hover:text-red-500"
                onClick={handleDelete}
                title="删除微博"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
                <span>删除</span>
              </button>

              <button
                className="inline-flex items-center gap-1.5 h-[30px] px-3 rounded-full border border-border bg-surface text-[11px] font-extrabold cursor-pointer transition-all hover:bg-gray-50 hover:border-gray-400 hover:text-gray-500"
                onClick={handleBlock}
                title="拉黑用户"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
                </svg>
                <span>拉黑</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
