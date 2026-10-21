import type { UserSummary } from "../types";
import { avatarColor, initials } from "../utils";

/** Initials on a colour derived from the user id (no uploads needed). */
export default function Avatar({ user, size = 40 }: { user: UserSummary; size?: 24 | 32 | 40 | 80 }) {
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, background: avatarColor(user.id), fontSize: size * 0.4 }}
      aria-hidden="true"
    >
      {initials(user.username)}
    </span>
  );
}
