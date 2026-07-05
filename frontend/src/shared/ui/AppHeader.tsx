import { m } from "#/paraglide/messages";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-50 w-full bg-slate text-slate-foreground border-b border-metal/30 shrink-0">
      <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4 sm:px-8">
        <div className="flex flex-col">
          <h1 className="font-display text-xl sm:text-2xl font-bold tracking-wide text-slate-foreground">
            {m.app_title()}
          </h1>
          <p className="hidden sm:block text-[10px] font-display uppercase tracking-[0.12em] text-metal-foreground">
            {m.app_subtitle()}
          </p>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
