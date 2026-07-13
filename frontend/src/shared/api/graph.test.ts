import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchNodes, fetchSubgraph } from "./graph";

function mockFetchOnce(response: Partial<Response> & { json?: () => unknown }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => undefined,
    ...response,
  } as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("fetchNodes", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed node list on a valid payload", async () => {
    mockFetchOnce({
      json: async () => ({
        nodes: [
          {
            id: "fear",
            label: "SpecialRule",
            name: "Fear",
            source_url: "https://x",
          },
        ],
      }),
    });

    const nodes = await fetchNodes({ q: "fear" });

    expect(nodes).toEqual([
      {
        id: "fear",
        label: "SpecialRule",
        name: "Fear",
        source_url: "https://x",
      },
    ]);
  });

  it("degrades to null on a malformed payload rather than throwing", async () => {
    mockFetchOnce({
      json: async () => ({ nodes: [{ label: "SpecialRule" }] }),
    }); // missing required id

    await expect(fetchNodes({ q: "fear" })).resolves.toBeNull();
  });

  it("returns null when the response is not ok", async () => {
    mockFetchOnce({ ok: false, status: 500 });

    await expect(fetchNodes()).resolves.toBeNull();
  });

  it("returns null when the fetch itself throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down")),
    );

    await expect(fetchNodes()).resolves.toBeNull();
  });

  it("builds the query string from nodeType/q/limit", async () => {
    const fetchMock = mockFetchOnce({ json: async () => ({ nodes: [] }) });

    await fetchNodes({ nodeType: "special_rule", q: "fear", limit: 5 });

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("node_type=special_rule");
    expect(calledUrl).toContain("q=fear");
    expect(calledUrl).toContain("limit=5");
  });
});

describe("fetchSubgraph", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed subgraph on a valid payload", async () => {
    mockFetchOnce({
      json: async () => ({
        nodes: [{ id: "fear", name: "Fear" }],
        edges: [{ source: "fear", target: "terror", rel_type: "REFERENCES" }],
      }),
    });

    const result = await fetchSubgraph("fear", 2);

    expect(result?.nodes).toHaveLength(1);
    expect(result?.edges).toEqual([
      { source: "fear", target: "terror", rel_type: "REFERENCES" },
    ]);
  });

  it("degrades to null when edges are malformed", async () => {
    mockFetchOnce({
      json: async () => ({
        nodes: [{ id: "fear" }],
        edges: [{ source: "fear" }], // missing target/rel_type
      }),
    });

    await expect(fetchSubgraph("fear")).resolves.toBeNull();
  });

  it("URL-encodes the node id", async () => {
    const fetchMock = mockFetchOnce({
      json: async () => ({ nodes: [], edges: [] }),
    });

    await fetchSubgraph("some id/with slash", 3);

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain(encodeURIComponent("some id/with slash"));
    expect(calledUrl).toContain("depth=3");
  });
});
