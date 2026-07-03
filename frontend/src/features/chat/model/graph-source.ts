import { z } from "zod";

/**
 * Schema for a single graph node returned by the backend as a "data-sources"
 * SSE event payload. Kept intentionally lenient on optional fields so that a
 * malformed optional value does not cause us to drop an otherwise usable
 * source array.
 */
export const graphSourceSchema = z.object({
  id: z.string(),
  label: z
    .string()
    .nullish()
    .transform((value) => value ?? undefined)
    .optional(),
  text: z
    .string()
    .nullish()
    .transform((value) => value ?? undefined)
    .optional(),
  source_url: z
    .string()
    .nullish()
    .transform((value) => value ?? undefined)
    .optional(),
});

export type GraphSource = z.infer<typeof graphSourceSchema>;

/**
 * Schema for the full "data-sources" payload.
 */
const graphSourcesSchema = z.array(graphSourceSchema);

/**
 * Lenient parser for graph source payloads.
 *
 * Returns a narrowed array on success, or `null` on failure. Failures are
 * logged but never thrown — this keeps the chat stream alive when the backend
 * emits an unexpected payload shape.
 */
export function parseGraphSources(data: unknown): GraphSource[] | null {
  const result = graphSourcesSchema.safeParse(data);

  if (!result.success) {
    console.warn("[Chat] Failed to parse graph sources", result.error.format());
    return null;
  }

  return result.data;
}

/**
 * SDK wiring for the "data-sources" part type.
 *
 * If we ever switch from the lenient reader model to strict SDK validation,
 * export the constant below and pass it to `useChat`'s `dataPartSchemas`
 * option:
 *
 *   export const chatDataPartSchemas = {
 *     "data-sources": graphSourcesSchema,
 *   } satisfies Record<string, z.ZodSchema>;
 *
 * Until then we validate at render time with `safeParse` so malformed payloads
 * are dropped without aborting the stream.
 */
