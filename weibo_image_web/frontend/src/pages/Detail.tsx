import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  fetchPost,
  fetchFavoriteIds,
  addFavorite,
  removeFavorite,
  deletePost,
  fetchPostTags,
  fetchTags,
  addTag,
  removeTag,
  addToBlacklist,
} from "../api";
import type { PostDetail as PostDetailType } from "../types";
import ImageViewer from "../components/ImageViewer";

function computeImageRows(total: number): number[] {
  if (total <= 0) return [];
  if (total <= 5) return [total];
  const numRows = Math.ceil(total / 4);
  const base = Math.floor(total / numRows);
  const extra = total % numRows;
  const rows: number[] = [];
  for (let i = 0; i < numRows; i++) {
    rows.push(base + (i < extra ? 1 : 0));
  }
  return rows;
}

export default function Detail() {
  const { uid = "", id = "" } = useParams();
  const navigate = useNavigate();
  const [post, setPost] = useState<PostDetailType | null>(null);
  const [isFav, setIsFav] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [postTags, setPostTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [allTags, setAllTags] = useState<string[]>([]);
  const [showTagInput, setShowTagInput] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const tagFormRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchPost(uid, id)
      .then(setPost)
      .catch(() => setPost(null));
    fetchFavoriteIds().then((ids) =>
      setIsFav(ids.includes(`${uid}_${id}`))
    );
    fetchPostTags(uid, id).then(setPostTags);
    fetchTags().then((tags) => setAllTags(tags.map((t) => t.tag)));
  }, [uid, id]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (tagFormRef.current && !tagFormRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const toggleFav = useCallback(async () => {
    if (isFav) {
      await removeFavorite(uid, id);
      setIsFav(false);
    } else {
      await addFavorite(uid, id);
      setIsFav(true);
    }
  }, [uid, id, isFav]);

  const handleDelete = useCallback(async () => {
    if (!window.confirm("确定删除这条微博？删除后会移入回收站。")) return;
    try {
      await deletePost(uid, id);
      navigate(-1);
    } catch {
      alert("删除失败");
    }
  }, [uid, id, navigate]);

  const handleBlock = useCallback(async () => {
    if (!window.confirm("确定拉黑该用户？拉黑后该用户的所有内容将不再显示。")) return;
    try {
      await addToBlacklist(uid);
      navigate("/");
    } catch {
      alert("拉黑失败");
    }
  }, [uid, navigate]);

  const handleAddTag = useCallback(async () => {
    const t = tagInput.trim();
    if (!t) return;
    try {
      await addTag(uid, id, t);
      setPostTags((prev) => (prev.includes(t) ? prev : [...prev, t]));
      if (!allTags.includes(t)) setAllTags((prev) => [...prev, t]);
      setTagInput("");
      setShowSuggestions(false);
      setShowTagInput(false);
    } catch {
      alert("添加标签失败");
    }
  }, [uid, id, tagInput, allTags]);

  const handleToggleSystemTag = useCallback(
    async (tag: string) => {
      if (postTags.includes(tag)) {
        try {
          await removeTag(tag, uid, id);
          setPostTags((prev) => prev.filter((t) => t !== tag));
        } catch {
          alert("移除标签失败");
        }
      } else {
        try {
          await addTag(uid, id, tag);
          setPostTags((prev) => [...prev, tag]);
        } catch {
          alert("添加标签失败");
        }
      }
    },
    [uid, id, postTags]
  );

  const handleRemoveTag = useCallback(
    async (tag: string) => {
      try {
        await removeTag(tag, uid, id);
        setPostTags((prev) => prev.filter((t) => t !== tag));
      } catch {
        alert("移除标签失败");
      }
    },
    [uid, id]
  );

  if (!post) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />
      </div>
    );
  }

  const timestamp = post.timestamp
    ? new Date(post.timestamp * 1000).toLocaleString("zh-CN")
    : "";

  return (
    <div className="flex flex-col lg:flex-row gap-10 xl:gap-14 min-h-[calc(100vh-60px-32px)] w-full max-w-[1600px] mx-auto pb-24">
      {/* ── Left: Media Content ── */}
      <div className="flex-1 min-w-0">
        {post.videos.length > 0 && (
          <div className="flex flex-col gap-4 mb-8">
            {post.videos.map((video, i) => (
              <video
                key={i}
                className="w-full rounded-xl bg-slate-900"
                src={video}
                controls
                preload="metadata"
              />
            ))}
          </div>
        )}

        {post.images.length > 0 && (() => {
          const rows = computeImageRows(post.images.length);
          let offset = 0;
          return (
            <div className="flex flex-col gap-2">
              {rows.map((count, rowIdx) => {
                const start = offset;
                offset += count;
                const gridCols = count <= 1 ? "grid-cols-1" : count === 2 ? "grid-cols-2" : count === 3 ? "grid-cols-3" : count === 4 ? "grid-cols-4" : "grid-cols-5";
                return (
                  <div
                    key={rowIdx}
                    className={`grid ${gridCols} gap-2 max-md:grid-cols-1 max-md:gap-2.5`}
                  >
                    {post.images.slice(start, start + count).map((img, i) => (
                      <img
                        key={start + i}
                        className="w-full aspect-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity object-cover max-md:rounded-xl"
                        src={img}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        onClick={() => setViewerIndex(start + i)}
                      />
                    ))}
                  </div>
                );
              })}
            </div>
          );
        })()}
      </div>

      {/* ── Right: Sidebar ── */}
      <aside className="w-full lg:w-[420px] xl:w-[460px] shrink-0 flex flex-col gap-6 lg:pt-4">

        {/* Top bar: back + actions */}
        <div className="flex items-center justify-between">
          <button
            className="w-10 h-10 flex items-center justify-center rounded-full border border-border bg-white hover:bg-surface-hover hover:text-primary transition-all duration-200"
            onClick={() => navigate(-1)}
            title="返回"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="19 12 5 12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleFav}
              className={`w-10 h-10 flex items-center justify-center rounded-full border transition-all duration-200 ${
                isFav
                  ? "bg-primary border-primary text-white shadow-[0_4px_12px_rgba(255,36,66,0.3)]"
                  : "bg-white border-border text-text hover:border-primary hover:text-primary hover:bg-primary-light"
              }`}
              title={isFav ? "取消收藏" : "加入收藏"}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill={isFav ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </button>

            <button
              onClick={() => window.open(post.url, "_blank")}
              className="w-10 h-10 flex items-center justify-center rounded-full bg-white border border-border text-text hover:bg-blue-50 hover:text-blue-500 hover:border-blue-400 transition-all duration-200"
              title="查看原微博"
            >
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </button>

            <button
              onClick={handleDelete}
              className="w-10 h-10 flex items-center justify-center rounded-full bg-white border border-border text-text-secondary hover:bg-red-50 hover:text-red-500 hover:border-red-300 transition-all duration-200"
              title="删除"
            >
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          </div>
        </div>

        {/* Author info */}
        <div className="flex items-center gap-4">
          <img
            className="rounded-full object-cover bg-[#eee] shrink-0"
            src={`/media/${encodeURIComponent(post.uid)}/user_avatar.jpg`}
            alt=""
            width={52}
            height={52}
            onError={(e) => { e.currentTarget.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3Crect fill='%23eee' width='1' height='1'/%3E%3C/svg%3E"; e.currentTarget.onerror = null; }}
          />
          <div className="flex flex-col min-w-0">
            <Link
              to={`/uid/${post.uid}`}
              className="text-lg font-bold text-text no-underline hover:text-primary transition-colors truncate"
            >
              {post.nickname || `UID: ${post.uid}`}
            </Link>
            {timestamp && (
              <div className="text-sm text-text-secondary mt-0.5">{timestamp}</div>
            )}
          </div>
        </div>

        {/* Content */}
        {post.content && (
          <div className="text-[15px] leading-[1.7] whitespace-pre-wrap break-all text-text">
            {post.content}
          </div>
        )}

        {/* Tags */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <div className="text-sm font-semibold text-text-secondary">标签</div>
            <div className="flex-1 h-px bg-surface-hover" />
          </div>

          <div className="flex flex-wrap gap-2">
            {allTags.map((tag) => {
              const active = postTags.includes(tag);
              return (
                <button
                  key={tag}
                  onClick={() => handleToggleSystemTag(tag)}
                  className={`inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-semibold transition-all duration-200 border cursor-pointer ${
                    active
                      ? "bg-primary border-primary text-white hover:bg-primary-dark"
                      : "bg-white border-border text-text-secondary hover:border-primary hover:text-primary"
                  }`}
                >
                  {active ? (
                    <>
                      #{tag}
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </>
                  ) : (
                    <>#{tag}</>
                  )}
                </button>
              );
            })}

            {/* Add tag input */}
            <div ref={tagFormRef} className="inline-flex items-center">
              {!showTagInput ? (
                <button
                  onClick={() => setShowTagInput(true)}
                  className="w-8 h-8 flex items-center justify-center rounded-full border border-dashed border-border bg-transparent text-text-secondary hover:border-primary hover:text-primary hover:bg-primary-light transition-all duration-200"
                  title="添加新标签"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </button>
              ) : (
                <form
                  className="flex items-center gap-1 bg-white border border-border rounded-full px-2 py-1 focus-within:border-primary focus-within:ring-[3px] focus-within:ring-primary/10 transition-all"
                  onSubmit={(e) => { e.preventDefault(); handleAddTag(); }}
                >
                  <input
                    type="text"
                    autoFocus
                    className="w-28 border-none outline-none bg-transparent text-sm font-medium px-2"
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
                    onClick={() => { setShowTagInput(false); setTagInput(""); }}
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
                      <div className="absolute top-full left-0 mt-1 max-h-[180px] overflow-y-auto bg-white border border-border rounded-xl shadow-xl z-[100] p-1 flex flex-col min-w-[140px]">
                        {suggestions.map((s) => (
                          <button
                            key={s}
                            className="text-left px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary-light hover:text-primary transition-colors cursor-pointer border-none bg-transparent"
                            onMouseDown={(e) => {
                              e.preventDefault();
                              handleToggleSystemTag(s);
                              setShowTagInput(false);
                              setTagInput("");
                            }}
                          >
                            #{s}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </form>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 mt-2 border-t border-border-light">
          <div className="flex items-center gap-3 text-xs text-text-secondary/50">
            <span>UID {post.uid}</span>
            <span>ID {post.id}</span>
          </div>
          <button
            onClick={handleBlock}
            className="text-xs font-medium text-text-secondary/40 hover:text-red-500 transition-colors bg-transparent border-none cursor-pointer"
          >
            拉黑
          </button>
        </div>
      </aside>

      {viewerIndex !== null && (
        <ImageViewer
          images={post.images}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onChange={setViewerIndex}
        />
      )}
    </div>
  );
}
