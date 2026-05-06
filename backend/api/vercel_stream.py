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
                    tool_id = msg.tool_call_id or f"sources_{uuid.uuid4().hex}"
                    payload = {
                        "type": "data-sources",
                        "id": tool_id,
                        "data": tool_data,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

            yield f"data: {json.dumps({'type': 'text-end', 'id': msg_id})}\n\n"
            yield f"data: {json.dumps({'type': 'finish-step'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'value': str(e)})}\n\n"
