"""FastAPI dependency providers.

All long-lived resources (Neo4j driver, embedding model) are created lazily and
cached for the lifetime of the process. The LLM is resolved via a provider
registry so adding a new provider is a one-line registration, not an edit to the
factory body (see ADR-0007).
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING, Callable

import neo4j

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from pipeline.graph import client as graph_client

logger = logging.getLogger(__name__)


def _ollama_llm() -> BaseChatModel:
    """Build the Ollama chat model from env."""
    kwargs: dict[str, object] = {
        "model": os.getenv("LLM_MODEL", "llama3.1"),
        "temperature": 0.2,
    }
    base_url = os.getenv("LOCAL_LLM_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOllama(**kwargs)


def _openai_llm() -> BaseChatModel:
    """Build the OpenAI chat model from env."""
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def _anthropic_llm() -> BaseChatModel:
    """Build the Anthropic chat model from env."""
    return ChatAnthropic(
        model=os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"),
        temperature=0.2,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


_LLM_REGISTRY: dict[str, Callable[[], BaseChatModel]] = {
    "ollama": _ollama_llm,
    "local": _ollama_llm,  # .env.example uses "local" for Ollama
    "openai": _openai_llm,
    "anthropic": _anthropic_llm,
}


def get_llm() -> BaseChatModel:
    """Resolve the configured LLM provider.

    Provider is read from ``LLM_PROVIDER`` (default ``ollama``). Supported:
    ``ollama``/``local``, ``openai``, ``anthropic``.
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    factory = _LLM_REGISTRY.get(provider)
    if factory is None:
        supported = ", ".join(sorted(_LLM_REGISTRY.keys()))
        raise ValueError(f"Unsupported LLM provider '{provider}'. Use one of: {supported}")
    logger.debug("Resolved LLM provider: %s", provider)
    return factory()


def get_driver() -> neo4j.Driver:
    """Return the singleton Neo4j driver."""
    return graph_client.get_driver()


@lru_cache(maxsize=1)
def get_embedder() -> "SentenceTransformer":
    """Return the singleton embedding model.

    Loads the model configured by ``EMBEDDING_MODEL`` (default
    ``paraphrase-multilingual-mpnet-base-v2``). The same model must be used at
    ingestion and query time (ADR-0001).
    """
    from sentence_transformers import SentenceTransformer

    model_name = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2")
    device = os.getenv("EMBEDDING_DEVICE", "cpu")
    logger.info("Loading embedding model: %s (device=%s)", model_name, device)
    return SentenceTransformer(model_name, device=device)
