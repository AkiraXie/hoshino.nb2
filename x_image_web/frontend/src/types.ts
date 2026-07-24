export interface PostSummary {
  uid: string;
  id: string;
  content: string;
  nickname: string;
  timestamp: number;
  url: string;
  likes: number;
  image_count: number;
  video_count: number;
  cover: string | null;
  repost?: RepostInfo | null;
}

export interface RepostInfo {
  uid: string;
  nickname: string;
  content: string;
  url: string;
}

export interface PostDetail extends PostSummary {
  images: string[];
  videos: string[];
}

export interface PostListResponse {
  total: number;
  page: number;
  size: number;
  items: PostSummary[];
}

export interface TopUidInfo {
  uid: string;
  nickname: string;
  count: number;
  posts: PostSummary[];
}
