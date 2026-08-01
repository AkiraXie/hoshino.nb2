import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchUids, fetchTopUids } from "../api";
import type { TopUidInfo } from "../types";

export default function Uids() {
  const [uids, setUids] = useState<Record<string, string>>({});
  const [topUids, setTopUids] = useState<TopUidInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchUids(), fetchTopUids(10, 0)])
      .then(([uidMap, top]) => {
        setUids(uidMap);
        setTopUids(top);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const sortedUids = Object.entries(uids).sort((a, b) =>
    (a[1] || a[0]).localeCompare(b[1] || b[0])
  );

  const topMap = new Map(topUids.map((t) => [t.uid, t.count]));

  return (
    <div>
      <h1 className="text-xl font-bold text-text-primary mb-6">用户列表</h1>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {sortedUids.map(([uid, nickname]) => (
            <Link
              key={uid}
              to={`/uid/${uid}`}
              className="flex items-center gap-3 p-4 bg-bg-card border border-border rounded-xl no-underline
                         hover:border-accent/40 hover:bg-bg-elevated transition-all group"
            >
              <span className="w-10 h-10 rounded-full bg-frost flex items-center justify-center text-sm text-ice font-bold shrink-0
                               group-hover:bg-accent/20 group-hover:text-accent-light transition-colors">
                {(nickname || uid)[0]?.toUpperCase()}
              </span>
              <div className="min-w-0">
                <div className="text-sm font-medium text-text-primary truncate group-hover:text-accent-light transition-colors">
                  {nickname || uid}
                </div>
                <div className="text-xs text-text-muted truncate">
                  @{uid}
                  {topMap.has(uid) && ` · ${topMap.get(uid)} 条`}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {!loading && sortedUids.length === 0 && (
        <div className="flex items-center justify-center h-64 text-text-muted">
          暂无用户数据
        </div>
      )}
    </div>
  );
}
