from typing import AsyncGenerator, Optional, List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from backend.api.vercel_stream import VercelStream

from backend.api.dependencies import get_llm

router = APIRouter()

class MessagePart(BaseModel):
    type: str
    text: str

class Message(BaseModel):
    role: str
    id: Optional[str] = None
    parts: Optional[List[MessagePart]] = None

    # 3. Add a helper property so your backend logic stays clean
    @property
    def text_content(self) -> str:
        return "".join(part.text for part in self.parts if part.type == "text")

class ChatRequest(BaseModel):
    messages: List[Message]

@router.post("/")
async def chat(
        request: ChatRequest,
        llm: BaseChatModel = Depends(get_llm)
) -> StreamingResponse:
    lc_messages = [SystemMessage(content="You are a helpful assistant expert in Warhammer: The Old World.")]

    for msg in request.messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.text_content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.text_content))
        elif msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.text_content))

    vercel_sse_stream = VercelStream.stream_langchain(llm.astream(lc_messages))

    return StreamingResponse(
        vercel_sse_stream,
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"}
    )