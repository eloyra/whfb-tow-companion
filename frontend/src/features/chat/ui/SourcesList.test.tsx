import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GraphSource } from "#/features/chat/model/graph-source";

import { SourcesList } from "./SourcesList";

const sources: GraphSource[] = [
  {
    id: "fear",
    label: "SpecialRule",
    text: "Fear forces the enemy unit to take a Panic test.",
    source_url: undefined,
  },
  {
    id: "blood-knights",
    label: "Unit",
    text: undefined,
    source_url: "https://example.com",
  },
];

describe("SourcesList", () => {
  it("renders a chip for each graph source", () => {
    render(<SourcesList sources={sources} />);

    expect(screen.getByText("fear")).toBeInTheDocument();
    expect(screen.getByText("blood-knights")).toBeInTheDocument();
  });

  it("renders the sources section label", () => {
    render(<SourcesList sources={sources} />);

    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("wraps a source with a valid URL in a link", () => {
    render(<SourcesList sources={sources} />);

    const link = screen.getByRole("link", { name: "blood-knights" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("renders the 'no sources' message for an empty array", () => {
    render(<SourcesList sources={[]} />);

    expect(screen.getByText("No sources retrieved")).toBeInTheDocument();
  });
});
