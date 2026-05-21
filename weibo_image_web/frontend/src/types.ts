export interface PostSummary {
  uid: string;
  id: string;
  content: string;
  nickname: string;
  timestamp: number;
  url: string;
  image_count: number;
  video_count: number;
  has_screenshot: boolean;
  cover: string | null;
}

export interface PostDetail extends PostSummary {
  images: string[];
  videos: string[];
  screenshot: string | null;
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

export interface TagInfo {
  tag: string;
  count: number;
}
