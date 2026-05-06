import os
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel
from langchain.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from backend.api.dependencies import get_llm
from backend.api.vercel_stream import VercelStream
from backend.rag.prompts.system_prompt import SYSTEM_PROMPT
from backend.rag.tools import AGENT_TOOLS

router = APIRouter()


class MessagePart(BaseModel):
    type: str
    text: str


class Message(BaseModel):
    role: str
    id: Optional[str] = None
    parts: Optional[List[MessagePart]] = None

    @property
    def text_content(self) -> str:
        if not self.parts:
            return ""
        return "".join(part.text for part in self.parts if part.type == "text")


class ChatRequest(BaseModel):
    messages: List[Message]


@router.post("/")
async def chat(
    request: ChatRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> StreamingResponse:
    lc_messages: list[AnyMessage] = []
    for msg in request.messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.text_content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.text_content))

    agent = create_agent(llm, tools=AGENT_TOOLS, system_prompt=SYSTEM_PROMPT)
    config = {
        "metadata": {"environment": os.getenv("ENVIRONMENT", "development")},
    }
    agent_stream = agent.astream(
        Command(update={"messages": lc_messages}),
        stream_mode="messages",
        config=config,
    )

    return StreamingResponse(
        VercelStream.stream_langgraph(agent_stream),
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
