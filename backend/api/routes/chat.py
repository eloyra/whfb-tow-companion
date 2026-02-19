from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    language: str = "en"
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    graph_nodes_used: list[str]
    language: str


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    # TODO: wire up RAG pipeline
    raise NotImplementedError
