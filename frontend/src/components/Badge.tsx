import { badgeLabel } from "../utils";

/** Unread count bubble; renders nothing at 0. */
export default function Badge({ count, label }: { count: number; label: string }) {
  if (count <= 0) return null;
  return (
    <span className="badge-count" aria-label={`${count} ${label}`}>
      {badgeLabel(count)}
    </span>
  );
}
