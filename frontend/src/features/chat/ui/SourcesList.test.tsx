import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// TanStack Router's Link needs a router context to render (it calls
// useLinkProps internally, which throws outside a RouterProvider); mock it to
// a plain anchor so this component test stays router-free, mirroring
// ChatInterface.test.tsx's approach to mocking framework hooks that otherwise
// require a provider.
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    search,
    children,
    ...props
  }: {
    to: string;
    search?: Record<string, string>;
    children?: ReactNode;
  }) => {
    const query = search ? `?${new URLSearchParams(search).toString()}` : "";
    return (
      <a href={`${to}${query}`} {...props}>
        {children}
      </a>
    );
  },
}));

import type { GraphSource } from "#/features/chat/model/graph-source";

import { SourcesList } from "./SourcesList";

const sources: GraphSource[] = [
  {
    id: "fear",
    name: "Fear",
    label: "SpecialRule",
    text: "Fear forces the enemy unit to take a Panic test.",
  },
  {
    id: "blood-knights",
    name: "Blood Knights",
    label: "Unit",
    source_url: "https://example.com",
  },
];

describe("SourcesList", () => {
  it("renders a chip for each graph source using the display name", () => {
    render(<SourcesList sources={sources} />);

    expect(screen.getByText("Fear")).toBeInTheDocument();
    expect(screen.getByText("Blood Knights")).toBeInTheDocument();
  });

  it("falls back to the source id when no name is provided", () => {
    render(<SourcesList sources={[{ id: "stubborn" }]} />);

    expect(screen.getByText("stubborn")).toBeInTheDocument();
  });

  it("renders the sources section label", () => {
    render(<SourcesList sources={sources} />);

    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("wraps a source with a valid URL in a link", () => {
    render(<SourcesList sources={sources} />);

    const link = screen.getByRole("link", { name: "Blood Knights" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("renders a hover iframe preview for sources with a URL", () => {
    render(<SourcesList sources={sources} />);

    const iframe = document.querySelector('iframe[src="https://example.com"]');
    expect(iframe).toBeInTheDocument();
  });

  it("renders the 'no sources' message for an empty array", () => {
    render(<SourcesList sources={[]} />);

    expect(screen.getByText("No sources retrieved")).toBeInTheDocument();
  });

  it("deep-links each source to the graph viewer by id", () => {
    render(<SourcesList sources={sources} />);

    const graphLink = screen.getByRole("link", { name: /View in graph: Fear/ });
    expect(graphLink).toHaveAttribute("href", "/graph?node=fear");
  });
});
