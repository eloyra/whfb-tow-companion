from typing import AsyncGenerator
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel

from backend.api.dependencies import get_llm

router = APIRouter()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[Message]
    language: str = "en"
    conversation_id: str | None = None

@router.post("/")
async def chat(
        request: ChatRequest,
        llm: BaseChatModel = Depends(get_llm)
) -> StreamingResponse:
    # 1. Convert standard JSON messages to LangChain message objects
    lc_messages = []

    # System prompt to enforce the domain rules
    lc_messages.append(
        SystemMessage(content="You are a helpful assistant expert in Warhammer: The Old World.")
    )

    for msg in request.messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.content))
        elif msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.content))

    # 2. Asynchronous generator to stream the LLM response chunks
    async def generate() -> AsyncGenerator[str, None]:
        async for chunk in llm.astream(lc_messages):
            yield chunk.content

    # 3. Return the stream directly to the client
    return StreamingResponse(generate(), media_type="text/plain")