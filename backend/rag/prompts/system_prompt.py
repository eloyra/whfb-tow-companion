"""System prompt for the chat agent.

The prompt is now composed per provider in ``templates.py`` (the tool-result
format and citation mechanics differ between Anthropic-native and legacy JSON
tool results). Import ``build_system_prompt`` from there for new code.

``SYSTEM_PROMPT`` is kept as the legacy fixed variant for existing importers
and tests that do not care about the provider split.
"""

from backend.rag.prompts.templates import build_system_prompt

SYSTEM_PROMPT = build_system_prompt(native_citations=False)

__all__ = ["SYSTEM_PROMPT", "build_system_prompt"]
