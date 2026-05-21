const cache = new Map<string, unknown>();

export function saveListCache<T>(key: string, entry: T) {
  cache.set(key, entry);
}

export function loadListCache<T>(key: string): T | null {
  return (cache.get(key) as T) ?? null;
}
