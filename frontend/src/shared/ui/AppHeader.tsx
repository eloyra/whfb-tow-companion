import { Link } from "@tanstack/react-router";
import { m } from "#/paraglide/messages";
import { ThemeToggle } from "./ThemeToggle";

const navLinkClassName =
  "text-sm font-display uppercase tracking-[0.08em] text-slate-foreground/70 hover:text-slate-foreground transition-colors";
const navLinkActiveProps = {
  className: "text-slate-foreground underline underline-offset-4",
};

export function AppHeader() {
  return (
    <header className="sticky top-0 z-50 w-full bg-slate text-slate-foreground border-b border-metal/30 shrink-0">
      <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4 sm:px-8">
        <div className="flex flex-col">
          <h1 className="font-display text-xl sm:text-2xl font-bold tracking-wide text-slate-foreground">
            {m.app_title()}
          </h1>
          <p className="hidden sm:block text-[10px] font-display uppercase tracking-[0.12em] text-slate-foreground/80">
            {m.app_subtitle()}
          </p>
        </div>

        <nav className="flex items-center gap-4 sm:gap-6">
          <Link
            to="/"
            className={navLinkClassName}
            activeProps={navLinkActiveProps}
          >
            {m.nav_chat()}
          </Link>
          <Link
            to="/graph"
            className={navLinkClassName}
            activeProps={navLinkActiveProps}
          >
            {m.nav_graph()}
          </Link>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
