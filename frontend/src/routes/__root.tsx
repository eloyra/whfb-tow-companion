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
import { ErrorBoundary } from "#/shared/ui/ErrorBoundary";
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
          <div className="spinner mb-4"></div>
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
