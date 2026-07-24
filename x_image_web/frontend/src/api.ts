import type { PostListResponse, PostDetail, TopUidInfo } from "./types";

const BASE = "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function fetchPosts(params: {
  page?: number;
  size?: number;
  uid?: string;
  q?: string;
}): Promise<PostListResponse> {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.size) sp.set("size", String(params.size));
  if (params.uid) sp.set("uid", params.uid);
  if (params.q) sp.set("q", params.q);
  return request(`/api/posts?${sp}`);
}

export function fetchPostDetail(uid: string, id: string): Promise<PostDetail> {
  return request(`/api/posts/${encodeURIComponent(uid)}/${encodeURIComponent(id)}`);
}

export function fetchUids(): Promise<Record<string, string>> {
  return request("/api/uids");
}

export function fetchTopUids(limit = 5, preview = 4): Promise<TopUidInfo[]> {
  return request(`/api/stats/top-uids?limit=${limit}&preview=${preview}`);
}

export function fetchFavoriteIds(): Promise<string[]> {
  return request("/api/favorites/ids");
}

export function fetchFavorites(page = 1, size = 20): Promise<PostListResponse> {
  return request(`/api/favorites?page=${page}&size=${size}`);
}

export function addFavorite(uid: string, id: string): Promise<{ ok: boolean }> {
  return request("/api/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid, id }),
  });
}

export function removeFavorite(uid: string, id: string): Promise<{ ok: boolean }> {
  return request(`/api/favorites/${encodeURIComponent(uid)}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function refreshIndex(): Promise<{ ok: boolean; count: number }> {
  return request("/api/refresh", { method: "POST" });
}

/** Build a media URL: local paths are served directly, remote URLs go through proxy */
export function mediaUrl(url: string): string {
  if (url.startsWith("/media/")) {
    return url;
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return `/media/proxy?url=${encodeURIComponent(url)}`;
  }
  return url;
}
