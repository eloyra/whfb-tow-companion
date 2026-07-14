import json
import re
import uuid
from typing import Any, AsyncIterator

from langchain.messages import AIMessageChunk, ToolMessage


def _sse(payload: dict[str, Any]) -> str:
    """Format a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _extract_text(content: Any) -> str:
    """Flatten LangChain message content into plain text.

    Anthropic returns content as a list of content blocks (e.g.
    ``[{"type": "text", "text": "..."}]``), so a simple string check drops the
    entire stream. OpenAI typically returns a plain string. This helper handles
    both safely.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") in {"text", "text_delta"}:
            return content.get("text") or content.get("delta") or ""
        return ""
    if isinstance(content, list):
        return "".join(_extract_text(item) for item in content)
    return ""


def _extract_reasoning(content: Any) -> str:
    """Return reasoning/thinking text from content blocks, if any.

    Anthropic extended thinking emits ``thinking`` blocks; LangChain's standard
    content-block format uses ``reasoning``. Both are handled so the backend can
    surface the model's reasoning stream to the UI without mixing it into the
    final answer text.
    """
    if isinstance(content, dict):
        if content.get("type") in {"thinking", "reasoning"}:
            return content.get("thinking") or content.get("reasoning") or ""
        return ""
    if isinstance(content, list):
        return "".join(_extract_reasoning(item) for item in content)
    return ""


def _extract_citations(content: Any) -> list[dict[str, Any]]:
    """Collect native citation objects from a LangChain message chunk.

    Anthropic surfaces citation deltas as ``text`` content blocks carrying a
    ``citations`` list. We return the raw citation dicts so the caller can map
    ``search_result_index`` (or other citation identifiers) to source metadata.
    """
    citations: list[dict[str, Any]] = []
    if isinstance(content, dict) and content.get("type") == "text":
        raw = content.get("citations")
        if isinstance(raw, list):
            citations.extend(raw)
    elif isinstance(content, list):
        for item in content:
            citations.extend(_extract_citations(item))
    return citations


def _strip_inline_slugs(text: str, source_ids: set[str]) -> str:
    """Remove ``[source-id]`` citation markers from assistant text.

    Only tokens matching a known source id are removed, so bracketed stat
    notation such as ``[D3]`` or ``[X+]`` is preserved.
    """
    if not source_ids:
        return text
    # Build a regex that matches any of the known ids inside square brackets.
    ids_pattern = "|".join(re.escape(sid) for sid in source_ids)
    return re.sub(rf"\[(?:{ids_pattern})\]", "", text)


class VercelStream:
    """
    Adapts a LangGraph ``stream_mode="messages"`` stream into the Vercel AI SDK
    UI Message Stream Protocol (SSE). The frontend reads this via the
    ``x-vercel-ai-ui-message-stream: v1`` header.

    Supports text deltas, reasoning start/delta/end events, and custom
    ``data-sources`` chips for cited graph nodes.
    """

    @staticmethod
    async def stream_langgraph(agent_stream: AsyncIterator[Any]) -> AsyncIterator[str]:
        msg_id = f"msg_{uuid.uuid4().hex}"

        # Final text assembled from text deltas.
        assistant_text_parts: list[str] = []

        # Native Anthropic citation state.
        search_results: list[dict[str, Any]] = []
        cited_indices: set[int] = set()
        source_ids: set[str] = set()

        # Legacy (non-Anthropic) citation state.
        candidate_sources: dict[str, dict[str, Any]] = {}
        legacy_cited_ids: set[str] = set()

        # Track whether a tool was called so we know whether to emit data-sources.
        tool_called = False

        # Track which protocol blocks have been opened so we can close them in
        # the right order and defer ``text-start`` until the first actual text.
        text_started = False
        reasoning_started = False
        reasoning_id: str | None = None

        try:
            async for msg, _metadata in agent_stream:
                if isinstance(msg, AIMessageChunk):
                    reasoning = _extract_reasoning(msg.content)
                    if reasoning:
                        if not reasoning_started:
                            reasoning_started = True
                            reasoning_id = f"reasoning_{uuid.uuid4().hex}"
                            yield _sse({"type": "reasoning-start", "id": reasoning_id})
                        yield _sse(
                            {
                                "type": "reasoning-delta",
                                "id": reasoning_id,
                                "delta": reasoning,
                            }
                        )
                    elif reasoning_started:
                        reasoning_started = False
                        yield _sse({"type": "reasoning-end", "id": reasoning_id})
                        reasoning_id = None

                    text = _extract_text(msg.content)
                    if text:
                        # Capture bracket-marker citations from the raw text
                        # before stripping known source slugs from the stream.
                        # These are captured on both paths: on the native
                        # Anthropic path they are the system prompt's required
                        # fallback for when Claude's automatic citation
                        # mechanism doesn't fire for a paraphrased (not
                        # verbatim-quoted) claim, so ``cited_indices`` alone
                        # would otherwise silently under-report sources.
                        for sid in set(re.findall(r"\[([a-z0-9][a-z0-9-]*)\]", text)):
                            if sid in source_ids:
                                legacy_cited_ids.add(sid)

                        # Capture Anthropic native citations.
                        for citation in _extract_citations(msg.content):
                            if citation.get("type") == "search_result_location":
                                idx = citation.get("search_result_index")
                                if isinstance(idx, int):
                                    cited_indices.add(idx)

                        text = _strip_inline_slugs(text, source_ids)
                        if text:
                            if not text_started:
                                text_started = True
                                yield _sse({"type": "text-start", "id": msg_id})
                            assistant_text_parts.append(text)
                            yield _sse(
                                {
                                    "type": "text-delta",
                                    "id": msg_id,
                                    "delta": text,
                                }
                            )

                elif isinstance(msg, ToolMessage):
                    tool_called = True

                    # A tool result means the assistant's reasoning/text block
                    # for this turn has ended; close any open reasoning block.
                    if reasoning_started:
                        reasoning_started = False
                        yield _sse({"type": "reasoning-end", "id": reasoning_id})
                        reasoning_id = None

                    # Source metadata travels out-of-band via the LangChain tool
                    # ``artifact`` (never sent to the model): Anthropic rejects a
                    # tool_result whose content mixes a text block with
                    # search_result blocks, so the sources list can't live inline
                    # alongside the search_result blocks anymore.
                    artifact = getattr(msg, "artifact", None)
                    raw_sources = artifact.get("sources") if isinstance(artifact, dict) else None

                    # Native Anthropic path: content is a list of search_result
                    # blocks; citations reference them by position via
                    # search_result_index, resolved against ``search_results``.
                    if isinstance(msg.content, list):
                        if isinstance(raw_sources, list):
                            search_results.extend(
                                src for src in raw_sources if isinstance(src, dict)
                            )
                            source_ids.update(
                                src.get("id")
                                for src in raw_sources
                                if isinstance(src, dict) and src.get("id")
                            )
                        continue

                    # Legacy path: tool result is a JSON string. Prefer the
                    # artifact if present; fall back to parsing the content for
                    # callers that don't attach one.
                    if not isinstance(raw_sources, list):
                        tool_content = _extract_text(msg.content)
                        try:
                            tool_data = json.loads(tool_content)
                        except (TypeError, ValueError):
                            continue
                        raw_sources = (
                            tool_data.get("sources") if isinstance(tool_data, dict) else None
                        )
                        if not isinstance(raw_sources, list):
                            raw_sources = []

                    # Collect candidates by id (deduped across multiple tool calls).
                    for src in raw_sources:
                        if not isinstance(src, dict):
                            continue
                        sid = src.get("id")
                        if not sid:
                            continue
                        candidate_sources[sid] = {
                            "id": sid,
                            "name": src.get("name"),
                            "label": src.get("label"),
                            "text": src.get("text"),
                            "source_url": src.get("source_url") or src.get("url"),
                            "book": src.get("book"),
                            "page": src.get("page"),
                        }
                        source_ids.add(sid)

            assistant_text = "".join(assistant_text_parts)

            # Close any trailing reasoning block before finalising text.
            if reasoning_started:
                reasoning_started = False
                yield _sse({"type": "reasoning-end", "id": reasoning_id})
                reasoning_id = None

            # Determine which sources to surface.
            if search_results:
                # Native Anthropic path: use the model's own citations,
                # unioned with the bracket-marker fallback (by source id) for
                # claims the automatic citation mechanism didn't annotate.
                by_id = {s.get("id"): s for s in search_results if s.get("id")}
                ordered_ids: list[str] = []
                seen_ids: set[str] = set()
                for idx in sorted(cited_indices):
                    if 0 <= idx < len(search_results):
                        sid = search_results[idx].get("id")
                        if sid and sid not in seen_ids:
                            seen_ids.add(sid)
                            ordered_ids.append(sid)
                for sid in legacy_cited_ids:
                    if sid in by_id and sid not in seen_ids:
                        seen_ids.add(sid)
                        ordered_ids.append(sid)
                displayed_sources = [by_id[sid] for sid in ordered_ids]
            else:
                # Legacy path: derive citations from inline markers captured
                # during streaming and from whole-token mentions in the prose.
                bracket_re = re.compile(r"\[.*?\]")
                text_without_brackets = bracket_re.sub(" ", assistant_text)
                mentioned_ids = {
                    sid
                    for sid in candidate_sources
                    if re.search(rf"\b{re.escape(sid)}\b", text_without_brackets, re.IGNORECASE)
                }
                used_ids = candidate_sources.keys() & (legacy_cited_ids | mentioned_ids)
                displayed_sources = [candidate_sources[sid] for sid in used_ids]

            if text_started:
                yield _sse({"type": "text-end", "id": msg_id})

            # Only emit a sources chip list if a tool was actually called this turn.
            if tool_called:
                yield _sse(
                    {
                        "type": "data-sources",
                        "id": msg_id,
                        "data": displayed_sources,
                    }
                )

            yield _sse({"type": "finish-step"})

        except Exception as e:
            yield _sse({"type": "error", "value": str(e)})
