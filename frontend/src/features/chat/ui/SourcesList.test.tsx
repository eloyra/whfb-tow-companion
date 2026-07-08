import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
