import json
import uuid
from typing import Any, AsyncIterator

from langchain.messages import AIMessageChunk, ToolMessage


class VercelStream:
    """
    Adapts a LangGraph `stream_mode="messages"` stream into the Vercel AI SDK v6
    UI Message Stream Protocol (SSE). The frontend reads this via the
    `x-vercel-ai-ui-message-stream: v1` header.
    """

    @staticmethod
    async def stream_langgraph(agent_stream: AsyncIterator[Any]) -> AsyncIterator[str]:
        msg_id = f"msg_{uuid.uuid4().hex}"

        yield f"data: {json.dumps({'type': 'text-start', 'id': msg_id})}\n\n"

        try:
            async for msg, _metadata in agent_stream:
                if isinstance(msg, AIMessageChunk):
                    if msg.content and isinstance(msg.content, str):
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

                    # The pipeline returns a dict with a "sources" array. The UI
                    # expects data-sources to be a flat list of source nodes so it
                    # can render them as clickable chips/links.
                    raw_sources = (
                        tool_data.get("sources")
                        if isinstance(tool_data, dict)
                        else None
                    )
                    if not isinstance(raw_sources, list):
                        raw_sources = []

                    # Normalize to the contract the frontend renderer expects.
                    sources = []
                    for src in raw_sources:
                        if not isinstance(src, dict):
                            continue
                        sources.append(
                            {
                                "id": src.get("id"),
                                "label": src.get("label"),
                                "text": src.get("text"),
                                "source_url": src.get("source_url") or src.get("url"),
                            }
                        )

                    tool_id = msg.tool_call_id or f"sources_{uuid.uuid4().hex}"
                    payload = {
                        "type": "data-sources",
                        "id": tool_id,
                        "data": sources,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

            yield f"data: {json.dumps({'type': 'text-end', 'id': msg_id})}\n\n"
            yield f"data: {json.dumps({'type': 'finish-step'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'value': str(e)})}\n\n"
