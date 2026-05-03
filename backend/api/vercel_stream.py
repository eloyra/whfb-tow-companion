import json
import uuid
from typing import AsyncIterator, Any


class VercelStream:
    """
    Implements the Vercel AI SDK v6 UI Message Stream Protocol.
    Uses Server-Sent Events (SSE) to populate the frontend's `message.parts` array.
    """

    @staticmethod
    async def stream_langchain(astream_generator: AsyncIterator[Any]) -> AsyncIterator[str]:
        # Generate a unique ID for this specific AI message response
        msg_id = f"msg_{uuid.uuid4().hex}"

        # 1. Announce the start of a text block
        start_payload = {"type": "text-start", "id": msg_id}
        yield f"data: {json.dumps(start_payload)}\n\n"

        try:
            # 2. Stream the deltas (the actual words)
            async for chunk in astream_generator:
                if chunk.content:
                    delta_payload = {"type": "text-delta", "id": msg_id, "delta": chunk.content}
                    yield f"data: {json.dumps(delta_payload)}\n\n"

            # 3. Announce the end of the text block
            end_payload = {"type": "text-end", "id": msg_id}
            yield f"data: {json.dumps(end_payload)}\n\n"

            # 4. (Optional but recommended) Close the step so Vercel knows we are done
            yield f"data: {json.dumps({'type': 'finish-step'})}\n\n"

        except Exception as e:
            # Vercel's protocol for catching backend errors and showing them in the UI
            error_payload = {"type": "error", "value": str(e)}
            yield f"data: {json.dumps(error_payload)}\n\n"