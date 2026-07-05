import { TanStackDevtools } from "@tanstack/react-devtools";
import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  HeadContent,
  Outlet,
  Scripts,
} from "@tanstack/react-router";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { ThemeProvider } from "next-themes";
import type * as React from "react";
import { useEffect } from "react";
import { m } from "#/paraglide/messages";
import { getLocale } from "#/paraglide/runtime";
import TanStackQueryDevtools from "#/shared/api/query/devtools";
import TanstackQueryProvider from "#/shared/api/query/root-provider";
import { ErrorBoundary } from "#/shared/ui";
import appCss from "../styles.css?url";

interface MyRouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
  beforeLoad: async () => {
    // Other redirect strategies are possible; see
    // https://github.com/TanStack/router/tree/main/examples/react/i18n-paraglide#offline-redirect
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("lang", getLocale());
    }
  },

  head: () => ({
    meta: [
      {
        charSet: "utf-8",
      },
      {
        name: "viewport",
        content: "width=device-width, initial-scale=1",
      },
      {
        title: m.app_title(),
      },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
    ],
  }),
  component: RootComponent,
  shellComponent: RootDocument,
});

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  useEffect(() => {
    const loader = document.getElementById("global-loader");

    if (loader) {
      loader.classList.add("loader-fade-out");
      setTimeout(() => loader.remove(), 500);
    }
  }, []);

  return (
    <TanstackQueryProvider queryClient={queryClient}>
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    </TanstackQueryProvider>
  );
}

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang={getLocale()} suppressHydrationWarning>
      <head>
        <title>{m.app_title()}</title>
        <HeadContent />
      </head>

      <body className="bg-background text-foreground" suppressHydrationWarning>
        <div id="global-loader">
          <svg
            width="56"
            height="56"
            viewBox="0 0 48 48"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="seal-pulse"
            aria-label="Loading"
          >
            <circle cx="24" cy="24" r="22" fill="var(--metal)" />
            <circle
              cx="24"
              cy="24"
              r="18"
              stroke="var(--metal-foreground)"
              strokeOpacity="0.3"
              strokeWidth="1"
            />
            <path
              d="M14 18L18 22"
              stroke="var(--metal-foreground)"
              strokeOpacity="0.25"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
            <path
              d="M30 30L34 34"
              stroke="var(--metal-foreground)"
              strokeOpacity="0.25"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
            <path
              d="M32 14L30 18"
              stroke="var(--metal-foreground)"
              strokeOpacity="0.2"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
            <path
              d="M24 16V32M17 24H31"
              stroke="var(--metal-foreground)"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </div>

        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}

          <TanStackDevtools
            config={{
              position: "bottom-right",
            }}
            plugins={[
              {
                name: "Tanstack Router",
                render: <TanStackRouterDevtoolsPanel />,
              },
              TanStackQueryDevtools,
            ]}
          />
          <Scripts />
        </ThemeProvider>
      </body>
    </html>
  );
}
