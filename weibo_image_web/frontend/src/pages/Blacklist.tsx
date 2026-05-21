import { useState, useEffect, useCallback } from "react";
import { fetchBlacklist, removeFromBlacklist } from "../api";
import type { BlacklistEntry } from "../api";
import UserAvatar from "../components/UserAvatar";

export default function Blacklist() {
  const [list, setList] = useState<BlacklistEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchBlacklist()
      .then(setList)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleUnblock = useCallback(async (uid: string) => {
    if (!window.confirm("确定取消拉黑该用户？")) return;
    try {
      await removeFromBlacklist(uid);
      setList((prev) => prev.filter((e) => e.uid !== uid));
    } catch {
      alert("操作失败");
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
      <div className="text-lg font-semibold mb-4 pl-1 flex items-center gap-2.5">黑名单</div>
      <div className="text-sm text-text-secondary/50 mb-6">{list.length} 位</div>
      <div className="flex flex-col gap-2">
        {list.map((entry) => (
          <div key={entry.uid} className="flex items-center gap-4 py-3 px-2 rounded-lg hover:bg-surface-hover transition-colors">
            <UserAvatar uid={entry.uid} size={48} />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-text truncate">{entry.nickname || entry.uid}</div>
              <div className="flex items-center gap-3 text-xs text-text-secondary/50 mt-0.5">
                <span>UID: {entry.uid}</span>
                <a
                  href={`https://weibo.com/u/${entry.uid}`}
                  className="text-primary/50 no-underline hover:text-primary transition-colors"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  微博主页
                </a>
              </div>
            </div>
            <button
              className="text-xs font-medium px-3 py-1.5 rounded-full border border-border bg-white text-text-secondary hover:border-primary hover:text-primary transition-all cursor-pointer"
              onClick={() => handleUnblock(entry.uid)}
            >
              取消拉黑
            </button>
          </div>
        ))}
      </div>
      {list.length === 0 && (
        <div className="text-center py-16 text-text-secondary">
          <p>黑名单为空</p>
        </div>
      )}
    </>
  );
}
