import type { LucideIcon } from "lucide-react";
import { cn } from "#/shared/lib/utils";

interface WaxSealProps {
  icon: LucideIcon;
  size?: number;
  className?: string;
  pulse?: boolean;
  "aria-label"?: string;
}

/**
 * A wax-seal motif used as the app's signature ornament.
 * Renders a solid seal with a subtle inner ring and crack lines.
 */
export function WaxSeal({
  icon: Icon,
  size = 48,
  className,
  pulse = false,
  "aria-label": ariaLabel,
}: WaxSealProps) {
  return (
    <div
      className={cn(
        "relative inline-flex items-center justify-center",
        pulse && "seal-pulse",
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden={ariaLabel ? undefined : true}
    >
      <svg
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="absolute inset-0"
        role={ariaLabel ? "img" : undefined}
        aria-label={ariaLabel}
        aria-hidden={ariaLabel ? undefined : true}
      >
        {/* Outer seal */}
        <circle cx="24" cy="24" r="22" className="fill-metal" />
        {/* Inner ring */}
        <circle
          cx="24"
          cy="24"
          r="18"
          className="stroke-metal-foreground/30"
          strokeWidth="1"
        />
        {/* Crack lines */}
        <path
          d="M14 18L18 22"
          className="stroke-metal-foreground/25"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M30 30L34 34"
          className="stroke-metal-foreground/25"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M32 14L30 18"
          className="stroke-metal-foreground/20"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
      <Icon
        className="relative z-10 text-metal-foreground"
        size={size * 0.45}
        strokeWidth={2}
        aria-hidden="true"
      />
    </div>
  );
}
