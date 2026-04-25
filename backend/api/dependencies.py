import os
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


def get_llm() -> BaseChatModel:
    """
    Dependency Injection factory for the LLM.
    Swaps seamlessly between local testing (Ollama) and commercial APIs.
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return ChatOllama(
            model=os.getenv("LLM_MODEL", "llama3.1"),
            temperature=0.2,
        )
    elif provider == "openai":
        return ChatOpenAI(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            api_key=os.getenv("OPENAI_API_KEY")
        )
    else:
        raise ValueError(f"Unsupported LLM Provider: {provider}")

# We will add get_retriever() here later for the Neo4j graph traversal.