import os
from dotenv import load_dotenv

# Load environment variables before initializing the app
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import chat, graph

app = FastAPI(
    title="Warhammer RAG API",
    description="GraphRAG-powered assistant for Warhammer: The Old World",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-vercel-ai-ui-message-stream"],
)

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}