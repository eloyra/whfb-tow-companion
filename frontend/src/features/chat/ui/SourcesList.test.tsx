import { act, fireEvent, render, screen } from "@testing-library/react";
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

  it("shows a hover preview card with the source's own text, not an iframe", () => {
    render(<SourcesList sources={sources} />);

    expect(document.querySelector("iframe")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Fear forces the enemy unit/),
    ).not.toBeInTheDocument();

    fireEvent.mouseEnter(
      screen.getByText("Fear").closest("div") as HTMLElement,
    );

    expect(screen.getByText(/Fear forces the enemy unit/)).toBeInTheDocument();
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("hides the preview again on mouse leave, after the hide delay", () => {
    vi.useFakeTimers();
    try {
      render(<SourcesList sources={sources} />);

      const trigger = screen.getByText("Fear").closest("div") as HTMLElement;
      fireEvent.mouseEnter(trigger);
      expect(
        screen.getByText(/Fear forces the enemy unit/),
      ).toBeInTheDocument();

      fireEvent.mouseLeave(trigger);
      // Still visible immediately after leaving — the delay is what lets the
      // mouse travel from the chip to the (gapped, portaled) preview card
      // without the card closing before the pointer ever reaches it.
      expect(
        screen.getByText(/Fear forces the enemy unit/),
      ).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(
        screen.queryByText(/Fear forces the enemy unit/),
      ).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancels the pending hide when the mouse enters the preview card itself", () => {
    // This is the actual fix: without it, moving the mouse from the chip to
    // the tooltip to scroll its text closes the tooltip before the pointer
    // arrives, since a mouseleave on the chip fires first.
    vi.useFakeTimers();
    try {
      render(<SourcesList sources={sources} />);

      const trigger = screen.getByText("Fear").closest("div") as HTMLElement;
      fireEvent.mouseEnter(trigger);
      fireEvent.mouseLeave(trigger);

      const tooltip = screen.getByRole("tooltip");
      fireEvent.mouseEnter(tooltip);

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(
        screen.getByText(/Fear forces the enemy unit/),
      ).toBeInTheDocument();

      fireEvent.mouseLeave(tooltip);
      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(
        screen.queryByText(/Fear forces the enemy unit/),
      ).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a preview even without a source_url, using text alone", () => {
    // "Fear" in the fixture has text but no source_url.
    render(<SourcesList sources={sources} />);

    fireEvent.mouseEnter(
      screen.getByText("Fear").closest("div") as HTMLElement,
    );
    expect(screen.getByText(/Fear forces the enemy unit/)).toBeInTheDocument();
  });

  it("hovering one chip does not reveal a different chip's preview", () => {
    // Regression test: the previous implementation used Tailwind's bare
    // `group-hover`, which matches *any* ancestor with class "group" —
    // including MessageBubble's own unrelated hover-actions group — so
    // hovering anywhere in the message row opened every citation's preview
    // at once. Each chip's preview must be scoped to that specific chip only.
    const twoTextSources: GraphSource[] = [
      { id: "fear", name: "Fear", text: "Fear forces a Panic test." },
      {
        id: "terror",
        name: "Terror",
        text: "Terror also forces a Break test.",
      },
    ];
    render(<SourcesList sources={twoTextSources} />);

    fireEvent.mouseEnter(
      screen.getByText("Fear").closest("div") as HTMLElement,
    );

    expect(screen.getByText(/Fear forces a Panic test/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Terror also forces a Break test/),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole("tooltip")).toHaveLength(1);
  });

  it("shows the rulebook and page number below the title when present", () => {
    const withCitation: GraphSource[] = [
      {
        id: "fear",
        name: "Fear",
        text: "Fear forces the enemy unit to take a Panic test.",
        book: "Warhammer: The Old World Rulebook",
        page: 94,
      },
    ];
    render(<SourcesList sources={withCitation} />);

    fireEvent.mouseEnter(
      screen.getByText("Fear").closest("div") as HTMLElement,
    );

    expect(
      screen.getByText("Warhammer: The Old World Rulebook, p. 94"),
    ).toBeInTheDocument();
  });

  it("omits the citation line entirely when the source has no book", () => {
    render(<SourcesList sources={sources} />);

    fireEvent.mouseEnter(
      screen.getByText("Fear").closest("div") as HTMLElement,
    );

    expect(screen.queryByText(/, p\. /)).not.toBeInTheDocument();
  });

  it("shows just the book name when no page number is available", () => {
    const bookOnly: GraphSource[] = [
      { id: "fear", name: "Fear", text: "...", book: "FAQ v2.1" },
    ];
    render(<SourcesList sources={bookOnly} />);

    fireEvent.mouseEnter(
      screen.getByText("Fear").closest("div") as HTMLElement,
    );

    expect(screen.getByText("FAQ v2.1")).toBeInTheDocument();
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
