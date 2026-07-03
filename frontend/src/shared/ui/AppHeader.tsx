import { m } from "#/paraglide/messages";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-sm shrink-0">
      <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4 sm:px-8">
        <div className="flex flex-col">
          <h1 className="font-display text-lg sm:text-xl font-bold tracking-wide text-foreground">
            {m.app_title()}
          </h1>
          <p className="hidden sm:block text-xs text-muted">
            {m.app_subtitle()}
          </p>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
