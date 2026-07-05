import { Compass, User } from "lucide-react";
import { WaxSeal } from "#/shared/ui/WaxSeal";

interface RoleAvatarProps {
  role: "user" | "assistant";
  size?: number;
}

/**
 * Visual role indicator for a chat message.
 * User messages use a slate circle to match the calm slate bubble;
 * the assistant uses the bronze wax-seal signature.
 */
export function RoleAvatar({ role, size = 28 }: RoleAvatarProps) {
  if (role === "user") {
    return (
      <div
        className="shrink-0 rounded-full flex items-center justify-center bg-slate text-slate-foreground"
        style={{ width: size, height: size }}
        role="img"
        aria-label="You"
      >
        <User size={size * 0.55} strokeWidth={2} aria-hidden="true" />
      </div>
    );
  }

  return (
    <WaxSeal
      icon={Compass}
      size={size}
      className="shrink-0"
      aria-label="Assistant"
    />
  );
}
