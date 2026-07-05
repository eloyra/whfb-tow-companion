import json
import uuid
from typing import Any, AsyncIterator

from langchain.messages import AIMessageChunk, ToolMessage


class VercelStream:
    """
    Adapts a LangGraph `stream_mode="messages"` stream into the Vercel AI SDK v6
    UI Message Stream Protocol (SSE). The frontend reads this via the
    `x-vercel-ai-ui-message-stream: v1` header.

    Source chips (`data-sources`) are emitted only for sources the model actually
    cites in its answer. The tool may return many candidates, but only those whose
    id appears in the final assistant text as ``[slug]`` are surfaced to the UI.
    """

    @staticmethod
    async def stream_langgraph(agent_stream: AsyncIterator[Any]) -> AsyncIterator[str]:
        msg_id = f"msg_{uuid.uuid4().hex}"

        yield f"data: {json.dumps({'type': 'text-start', 'id': msg_id})}\n\n"

        # Candidates come from ToolMessages; the final text from AIMessageChunks.
        candidate_sources: dict[str, dict[str, Any]] = {}
        assistant_text_parts: list[str] = []

        try:
            async for msg, _metadata in agent_stream:
                if isinstance(msg, AIMessageChunk):
                    if msg.content and isinstance(msg.content, str):
                        assistant_text_parts.append(msg.content)
                        payload = {
                            "type": "text-delta",
                            "id": msg_id,
                            "delta": msg.content,
                        }
                        yield f"data: {json.dumps(payload)}\n\n"

                elif isinstance(msg, ToolMessage):
                    try:
                        tool_data = json.loads(msg.content)
                    except (TypeError, ValueError):
                        continue

                    raw_sources = (
                        tool_data.get("sources")
                        if isinstance(tool_data, dict)
                        else None
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
                            "label": src.get("label"),
                            "text": src.get("text"),
                            "source_url": src.get("source_url") or src.get("url"),
                        }

            assistant_text = "".join(assistant_text_parts)
            used_sources = [
                candidate_sources[sid]
                for sid in candidate_sources
                if f"[{sid}]" in assistant_text
            ]

            yield f"data: {json.dumps({'type': 'text-end', 'id': msg_id})}\n\n"

            # Only emit a sources chip list if a tool was actually called this turn.
            if candidate_sources:
                payload = {
                    "type": "data-sources",
                    "id": msg_id,
                    "data": used_sources,
                }
                yield f"data: {json.dumps(payload)}\n\n"

            yield f"data: {json.dumps({'type': 'finish-step'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'value': str(e)})}\n\n"
