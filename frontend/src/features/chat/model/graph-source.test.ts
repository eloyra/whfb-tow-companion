import { describe, expect, it } from "vitest";

import { parseGraphSources } from "./graph-source";

describe("parseGraphSources", () => {
  it("parses a well-formed source array", () => {
    const data = [
      {
        id: "fear",
        name: "Fear",
        label: "SpecialRule",
        text: "Fear forces the enemy unit to take a Panic test.",
        source_url: "https://tow.whfb.app/special-rules/fear",
      },
    ];

    expect(parseGraphSources(data)).toEqual(data);
  });

  it("accepts a source with only the required id field", () => {
    const result = parseGraphSources([{ id: "stubborn" }]);

    expect(result).toEqual([{ id: "stubborn" }]);
  });

  it("normalizes a null optional field to undefined instead of failing", () => {
    const result = parseGraphSources([{ id: "fear", name: null, text: null }]);

    expect(result).toEqual([{ id: "fear", name: undefined, text: undefined }]);
  });

  it("returns null (not a throw) when an entry is missing the required id", () => {
    expect(parseGraphSources([{ name: "Fear" }])).toBeNull();
  });

  it("returns null for a non-array payload", () => {
    expect(parseGraphSources({ id: "fear" })).toBeNull();
    expect(parseGraphSources(null)).toBeNull();
    expect(parseGraphSources(undefined)).toBeNull();
  });

  it("returns an empty array for an empty payload", () => {
    expect(parseGraphSources([])).toEqual([]);
  });
});
