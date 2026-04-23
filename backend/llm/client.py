"""
LLM abstraction layer. Swap providers without touching RAG pipeline code.
Reads LLM_PROVIDER and LLM_MODEL from environment.
"""

import os
from typing import Protocol

from dotenv import load_dotenv

load_dotenv()


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def get_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "openai")

    if provider == "openai":
        from backend.llm._openai import OpenAIClient

        return OpenAIClient()
    elif provider == "anthropic":
        from backend.llm._anthropic import AnthropicClient

        return AnthropicClient()
    elif provider == "local":
        from backend.llm._local import LocalClient

        return LocalClient()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
