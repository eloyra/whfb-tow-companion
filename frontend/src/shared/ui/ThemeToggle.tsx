import { Button } from "@heroui/react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <Button
        isIconOnly
        variant="ghost"
        isDisabled
        className="h-10 w-10 border border-metal/30 opacity-50"
        aria-label="Toggle theme"
      >
        <Sun size={18} aria-hidden="true" />
      </Button>
    );
  }

  const isDark = theme === "dark";

  return (
    <Button
      isIconOnly
      variant="ghost"
      onPress={() => setTheme(isDark ? "light" : "dark")}
      aria-label="Toggle theme"
      className="h-10 w-10 border border-metal/30 hover:bg-metal/10 hover:border-metal/60 focus-visible:ring-2 focus-visible:ring-metal/40"
    >
      {isDark ? (
        <Sun size={18} className="text-metal" aria-hidden="true" />
      ) : (
        <Moon size={18} className="text-metal" aria-hidden="true" />
      )}
    </Button>
  );
}
