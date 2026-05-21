import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { fetchTags } from "../api";
import type { TagInfo } from "../types";

export default function Tags() {
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTags()
      .then(setTags)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-8 text-text-secondary text-sm">
        <div className="w-7 h-7 border-[3px] border-border border-t-primary rounded-full animate-[spin_0.8s_linear_infinite]" />
      </div>
    );
  }

  return (
    <>
      <div className="text-lg font-semibold mb-4 pl-1 flex items-center gap-2.5">标签分类</div>
      <div className="text-sm text-text-secondary/50 mb-6">{tags.length} 个标签</div>

      {tags.length === 0 ? (
        <div className="text-center py-16 text-text-secondary">
          <p>还没有标签哦</p>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          {tags.map((t) => (
            <Link
              key={t.tag}
              to={`/tags/${encodeURIComponent(t.tag)}`}
              className="inline-flex items-center gap-3 px-6 py-3 rounded-full border border-border text-text-secondary no-underline hover:border-primary hover:text-primary hover:bg-primary-light transition-all duration-200 text-sm font-semibold"
            >
              {t.tag}
              <span className="text-xs font-bold bg-tag-bg text-tag-text px-2 py-0.5 rounded-full">{t.count}</span>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
