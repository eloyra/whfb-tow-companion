import os

from dotenv import load_dotenv

# Load environment variables before initializing the app
load_dotenv()

# Tag all LangSmith traces with the current environment so dev/staging/prod
# runs are separable in the LangSmith UI without switching projects.
if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
    env = os.getenv("ENVIRONMENT", "development")
    os.environ["LANGSMITH_TAGS"] = f'["env:{env}"]'

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.api.routes import chat, graph  # noqa: E402

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
