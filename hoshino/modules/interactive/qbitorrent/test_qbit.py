"""qBittorrent v4.5.x 登录与获取种子列表诊断脚本
用法: uv run python hoshino/modules/interactive/qbitorrent/test_qbit.py
"""

import asyncio
import sys
import httpx

# ====== 配置区 (来自 data/db/qbitorrent.db) ======
BASE_URL = "http://127.0.0.1:8080"
USERNAME = "admin"
PASSWORD = "adminadmin"
CATEGORY = "hoshino"
# ================================================

STATE_MAP = {
    "downloading": "下载中", "uploading": "上传中",
    "pausedDL": "暂停下载", "pausedUP": "暂停上传",
    "queuedDL": "排队下载", "queuedUP": "排队上传",
    "stalledDL": "停滞下载", "stalledUP": "停滞上传",
    "checkingDL": "检查中", "checkingUP": "检查中",
    "queuedForChecking": "等待检查", "checkingResumeData": "检查数据",
    "moving": "移动中", "unknown": "未知",
    "error": "错误", "missingFiles": "文件缺失",
    "allocating": "分配空间",
}


def fmt_size(s: int) -> str:
    if s > 1024**3:
        return f"{s / (1024**3):.1f} GB"
    elif s > 1024**2:
        return f"{s / (1024**2):.1f} MB"
    else:
        return f"{s / 1024:.1f} KB"


async def test():
    async with httpx.AsyncClient(timeout=30.0, verify=False) as cli:
        # ── 1. 登录 ──
        print("=" * 60)
        print(f"登录测试 → {BASE_URL}/api/v2/auth/login")
        print(f"用户名: {USERNAME}")
        print("=" * 60)

        r = await cli.post(
            f"{BASE_URL}/api/v2/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
        )
        print(f"status: {r.status_code}")
        print(f"set-cookie header: {r.headers.get('set-cookie', '(none)')}")
        print(f"httpx cookies dict: {dict(r.cookies)}")
        print(f"body: {r.text[:200]}")

        sid = r.cookies.get("SID")
        if not sid and r.status_code == 200:
            # 有时 cookie 名可能是小写
            for k, v in r.cookies.items():
                if k.lower() == "sid":
                    sid = v
                    print(f"⚠️ 找到变体 cookie: {k}={v[:16]}...")
                    break

        if not sid:
            print("\n❌ 登录失败: 未获取到 SID cookie")
            print("请检查 BASE_URL/USERNAME/PASSWORD 是否正确")
            return

        print(f"\n✅ 登录成功: SID={sid[:16]}...")

        # ── 2. 获取列表 ──
        for label, filter_ in [("活跃", "active"), ("已完成", "completed")]:
            print(f"\n── {label}列表 ──")
            params = {"category": CATEGORY}
            if filter_:
                params["filter"] = filter_
            r = await cli.get(
                f"{BASE_URL}/api/v2/torrents/info",
                headers={"Cookie": f"SID={sid}"},
                params=params,
            )
            print(f"status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"结果数: {len(data)}")
                for t in data[:5]:
                    print(f"  [{STATE_MAP.get(t.get('state',''), t.get('state',''))}] "
                          f"{t.get('name','?')[:40]} | {fmt_size(t.get('size',0))} | "
                          f"{t.get('progress',0)*100:.1f}%")
                if len(data) > 5:
                    print(f"  ... 还有 {len(data) - 5} 个")
            elif r.status_code == 403:
                print("❌ 403 Forbidden — SID 无效或已过期")
            else:
                print(f"body: {r.text[:300]}")

        # ── 3. 二次请求验证 session 持久性 ──
        print(f"\n── 二次请求 (验证 session 持久性) ──")
        r2 = await cli.get(
            f"{BASE_URL}/api/v2/torrents/info",
            headers={"Cookie": f"SID={sid}"},
            params={"category": CATEGORY},
        )
        if r2.status_code == 200:
            print(f"✅ Session 正常, 结果数: {len(r2.json())}")
        else:
            print(f"❌ Session 失效: status={r2.status_code}")

        # ── 4. 诊断结论 ──
        print(f"\n{'=' * 60}")
        print("诊断结论:")
        print(f"  登录方式: form-data (正确用于 v4.5.x)")
        print(f"  SID 获取: {'正常' if sid else '失败'}")
        print(f"  若列表为空但 status=200: 可能 CATEGORY='{CATEGORY}' 下无种子，或 filter 过滤后无结果")
        print(f"  若 status=403: SID 过期或无效，需重新登录")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(test())
