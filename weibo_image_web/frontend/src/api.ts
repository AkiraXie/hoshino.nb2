import type { PostDetail, PostListResponse, TopUidInfo, TagInfo } from "./types";

export async function fetchPosts(params: {
  page?: number;
  size?: number;
  uid?: string;
  q?: string;
  date?: string;
}): Promise<PostListResponse> {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.size) sp.set("size", String(params.size));
  if (params.uid) sp.set("uid", params.uid);
  if (params.q) sp.set("q", params.q);
  if (params.date) sp.set("date", params.date);
  const res = await fetch(`/api/posts?${sp}`);
  return res.json();
}

export async function fetchPost(
  uid: string,
  id: string
): Promise<PostDetail> {
  const res = await fetch(`/api/posts/${encodeURIComponent(uid)}/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Post not found");
  return res.json();
}

export async function fetchFavorites(params: {
  page?: number;
  size?: number;
}): Promise<PostListResponse> {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.size) sp.set("size", String(params.size));
  const res = await fetch(`/api/favorites?${sp}`);
  return res.json();
}

export async function fetchFavoriteIds(): Promise<string[]> {
  const res = await fetch("/api/favorites/ids");
  return res.json();
}

export async function addFavorite(uid: string, id: string): Promise<void> {
  await fetch("/api/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid, id }),
  });
}

export async function removeFavorite(
  uid: string,
  id: string
): Promise<void> {
  await fetch(`/api/favorites/${encodeURIComponent(uid)}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function refreshIndex(): Promise<{ ok: boolean; count: number }> {
  const res = await fetch("/api/refresh", { method: "POST" });
  return res.json();
}

export async function deletePost(
  uid: string,
  id: string
): Promise<{ ok: boolean }> {
  const res = await fetch(
    `/api/posts/${encodeURIComponent(uid)}/${encodeURIComponent(id)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Delete failed");
  return res.json();
}

export async function fetchUids(): Promise<Record<string, string>> {
  const res = await fetch("/api/uids");
  return res.json();
}

export async function fetchUidStats(): Promise<Record<string, { image_count: number; fav_count: number }>> {
  const res = await fetch("/api/uid-stats");
  return res.json();
}

export async function fetchTopUids(params?: {
  limit?: number;
  preview?: number;
  date?: string;
}): Promise<TopUidInfo[]> {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.preview) sp.set("preview", String(params.preview));
  if (params?.date) sp.set("date", params.date);
  const res = await fetch(`/api/stats/top-uids?${sp}`);
  return res.json();
}

// ── Tags ──────────────────────────────────────────────

export async function fetchTags(): Promise<TagInfo[]> {
  const res = await fetch("/api/tags");
  if (!res.ok) return [];
  return res.json();
}

export async function fetchTagPosts(
  tag: string,
  params: { page?: number; size?: number }
): Promise<PostListResponse> {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.size) sp.set("size", String(params.size));
  const res = await fetch(`/api/tags/${encodeURIComponent(tag)}?${sp}`);
  return res.json();
}

export async function fetchPostTags(
  uid: string,
  id: string
): Promise<string[]> {
  const res = await fetch(
    `/api/posts/${encodeURIComponent(uid)}/${encodeURIComponent(id)}/tags`
  );
  if (!res.ok) return [];
  return res.json();
}

export async function addTag(
  uid: string,
  id: string,
  tag: string
): Promise<void> {
  const res = await fetch("/api/tags", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid, id, tag }),
  });
  if (!res.ok) throw new Error("Failed to add tag");
}

export async function removeTag(
  tag: string,
  uid: string,
  id: string
): Promise<void> {
  const res = await fetch(
    `/api/tags/${encodeURIComponent(tag)}/${encodeURIComponent(uid)}/${encodeURIComponent(id)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to remove tag");
}

// ── Blacklist ─────────────────────────────────────────

export interface BlacklistEntry {
  uid: string;
  nickname: string;
}

export async function fetchBlacklist(): Promise<BlacklistEntry[]> {
  const res = await fetch("/api/blacklist");
  return res.json();
}

export async function addToBlacklist(uid: string): Promise<void> {
  await fetch("/api/blacklist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid }),
  });
}

export async function removeFromBlacklist(uid: string): Promise<void> {
  const res = await fetch(`/api/blacklist/${encodeURIComponent(uid)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to remove from blacklist");
}
