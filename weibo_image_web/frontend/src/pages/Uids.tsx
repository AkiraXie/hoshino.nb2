import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchUids, fetchUidStats, addToBlacklist } from "../api";
import UserAvatar from "../components/UserAvatar";

export default function Uids() {
  const [uids, setUids] = useState<Record<string, string>>({});
  const [stats, setStats] = useState<Record<string, { image_count: number; fav_count: number }>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchUids(), fetchUidStats()])
      .then(([u, s]) => { setUids(u); setStats(s); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const entries = Object.entries(uids).sort((a, b) =>
    a[1].localeCompare(b[1], "zh-CN")
  );

  const handleBlock = useCallback(async (uid: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("确定拉黑该用户？拉黑后该用户的所有内容将不再显示。")) return;
    try {
      await addToBlacklist(uid);
      setUids((prev) => {
        const next = { ...prev };
        delete next[uid];
        return next;
      });
    } catch {
      alert("拉黑失败");
    }
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
      <div className="text-lg font-semibold mb-4 pl-1 flex items-center gap-2.5">用户列表</div>
      <div className="text-sm text-text-secondary/50 mb-6">{entries.length} 位博主</div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
        {entries.map(([uid, nickname]) => {
          const s = stats[uid];
          return (
            <Link key={uid} to={`/uid/${uid}`} className="flex items-center gap-4 py-4 px-2 no-underline text-text hover:bg-surface-hover rounded-lg transition-colors group">
              <UserAvatar uid={uid} size={52} />
              <div className="flex-1 min-w-0">
                <div className="text-base font-semibold text-text mb-0.5 truncate group-hover:text-primary transition-colors">{nickname || uid}</div>
                <div className="flex items-center gap-3 text-xs text-text-secondary/50">
                  <span>UID: {uid}</span>
                  <a
                    href={`https://weibo.com/u/${uid}`}
                    className="text-primary/50 no-underline hover:text-primary transition-colors"
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    微博主页
                  </a>
                </div>
                {s && (
                  <div className="flex items-center gap-3 mt-1 text-xs text-text-secondary/40">
                    <span>{s.image_count} 张图</span>
                    {s.fav_count > 0 && <span>{s.fav_count} 收藏</span>}
                  </div>
                )}
              </div>
              <button
                className="shrink-0 w-8 h-8 flex items-center justify-center rounded-full border border-transparent hover:border-red-200 hover:bg-red-50 hover:text-red-500 transition-all text-text-secondary/30 bg-transparent cursor-pointer text-base"
                onClick={(e) => handleBlock(uid, e)}
                title="拉黑"
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
                </svg>
              </button>
            </Link>
          );
        })}
      </div>
      {entries.length === 0 && (
        <div className="text-center py-16 text-text-secondary">
          <p>暂无用户数据</p>
        </div>
      )}
    </>
  );
}
