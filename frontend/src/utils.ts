export function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString();
}

/** Keep the first occurrence of each id.
 *
 * Lists can receive the same item twice: a post created while the first page
 * is loading may come back in that page too, and with offset pagination new
 * posts shift the next page so it repeats items already shown.
 */
export function uniqueById<T extends { id: number }>(items: T[]): T[] {
  const seen = new Set<number>();
  return items.filter((item) => !seen.has(item.id) && seen.add(item.id));
}

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong";
}

// mirrors the backend limits so users get instant feedback
export const MAX_IMAGE_MB = 5;
export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
