"""Runners for retrieval-only and full-agent evaluation."""

from __future__ import annotations

from typing import Any

from backend.api.dependencies import get_driver, get_embedder, resolve_rag_mode
from backend.rag.retriever import GraphRAGRetriever
from tests.evaluation.models import AgentResult, JudgeVerdict, Query, RetrievalResult
from tests.evaluation.scoring import build_retrieval_result


def build_retriever(top_k: int = 8, mode: str = "graph") -> GraphRAGRetriever:
    """Build a retriever wired to the configured Neo4j instance.

    ``mode`` selects the retrieval-mode ablation variant (``vector`` /
    ``graph`` / ``hybrid``) via ``resolve_rag_mode`` — see ADR-0008.
    """
    strategy, lexical_fallback, _ = resolve_rag_mode(mode)
    driver = get_driver()
    embedder = get_embedder()
    return GraphRAGRetriever(
        driver, embedder, top_k=top_k, strategy=strategy, lexical_fallback=lexical_fallback
    )


def run_retrieval_evaluation(
    queries: list[Query],
    *,
    top_k: int = 8,
    mode: str = "graph",
) -> list[RetrievalResult]:
    """Run the retrieval-only pass over the golden set.

    Returns one ``RetrievalResult`` per query, containing recall@k and army
    presence flags.
    """
    retriever = build_retriever(top_k=top_k, mode=mode)
    results: list[RetrievalResult] = []
    for query in queries:
        seeds = retriever.retrieve(query.query)
        retrieved_ids = [seed["id"] for seed in seeds]
        results.append(
            build_retrieval_result(
                query_id=query.id,
                query=query.query,
                category=query.category,
                expected_rules=query.expected_rules,
                expected_army=query.expected_army,
                retrieved=retrieved_ids,
                k=top_k,
            )
        )
    return results


def _extract_cited_ids_from_tool_message(msg: Any) -> list[str]:
    """Pull candidate source ids out of a ``ToolMessage``.

    Source metadata travels via the LangChain tool ``artifact`` (never sent to
    the model — see ``backend/rag/tools.py``), so it's read from there first.
    Falls back to parsing ``content`` for messages built without an artifact.
    """
    import json

    artifact = getattr(msg, "artifact", None)
    if isinstance(artifact, dict) and isinstance(artifact.get("sources"), list):
        return [
            src["id"] for src in artifact["sources"] if isinstance(src, dict) and src.get("id")
        ]

    content = getattr(msg, "content", None)
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            return []
        if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            return [
                src["id"] for src in payload["sources"] if isinstance(src, dict) and src.get("id")
            ]
    return []


async def run_full_evaluation(
    queries: list[Query],
    *,
    top_k: int = 8,
    judge_llm: Any | None = None,
    mode: str = "graph",
) -> list[AgentResult]:
    """Run the full agent + optional LLM-judge pass over the golden set.

    If ``judge_llm`` is not provided, the agent answer and citations are
    recorded but ``verdict`` is left as ``None``. ``mode`` (``vector`` /
    ``graph`` / ``hybrid``) is applied via the ``RAG_MODE`` env var for the
    duration of this call, since the agent's tools are built from
    ``get_rag_pipeline()``, which reads that env var (ADR-0008).
    """
    import os

    from langchain.agents import create_agent
    from langchain.messages import AIMessage, AnyMessage, HumanMessage
    from langgraph.types import Command

    from backend.api.dependencies import get_llm
    from backend.api.dependencies import get_rag_pipeline as _get_rag_pipeline
    from backend.rag.prompts.templates import build_system_prompt
    from backend.rag.tools import build_tools

    retriever = build_retriever(top_k=top_k, mode=mode)
    previous_mode = os.environ.get("RAG_MODE")
    os.environ["RAG_MODE"] = mode
    try:
        pipeline = _get_rag_pipeline()
    finally:
        if previous_mode is None:
            os.environ.pop("RAG_MODE", None)
        else:
            os.environ["RAG_MODE"] = previous_mode
    llm = get_llm()
    tools = build_tools(pipeline)
    agent = create_agent(llm, tools=tools, system_prompt=build_system_prompt())
    config = {"metadata": {"environment": os.getenv("ENVIRONMENT", "evaluation")}}

    results: list[AgentResult] = []
    for query in queries:
        messages: list[AnyMessage] = [HumanMessage(content=query.query)]
        final_state = await agent.ainvoke(
            Command(update={"messages": messages}),
            config=config,
        )
        final_messages = final_state.get("messages", [])
        answer_parts = []
        cited_ids: list[str] = []
        for msg in final_messages:
            if isinstance(msg, AIMessage):
                answer_parts.append(str(msg.content))
            # ToolMessage is in langchain_core.messages, but importing here
            # avoids an unconditional dependency at module load time.
            if hasattr(msg, "tool_calls") and getattr(msg, "tool_calls", None):
                pass  # tool-call metadata, not a result payload
            if msg.type == "tool":
                cited_ids.extend(_extract_cited_ids_from_tool_message(msg))

        answer = "\n".join(answer_parts)
        seeds = retriever.retrieve(query.query)
        retrieved_ids = [seed["id"] for seed in seeds]
        retrieval = build_retrieval_result(
            query_id=query.id,
            query=query.query,
            category=query.category,
            expected_rules=query.expected_rules,
            expected_army=query.expected_army,
            retrieved=retrieved_ids,
            k=top_k,
        )

        verdict: JudgeVerdict | None = None
        if judge_llm is not None:
            verdict = await _run_judge(judge_llm, query, answer, cited_ids)

        results.append(
            AgentResult(
                query_id=query.id,
                query=query.query,
                category=query.category,
                answer=answer,
                cited_ids=sorted(set(cited_ids)),
                expected_rules=query.expected_rules,
                expected_army=query.expected_army,
                retrieval=retrieval,
                verdict=verdict,
            )
        )
    return results


async def _run_judge(
    judge_llm: Any,
    query: Query,
    answer: str,
    cited_ids: list[str],
) -> JudgeVerdict:
    """Ask an LLM to score the answer against the query rubric."""
    from langchain_core.output_parsers import PydanticOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    parser = PydanticOutputParser(pydantic_object=JudgeVerdict)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert judge evaluating answers from a Warhammer: "
                "The Old World assistant. Score the answer against the rubric on "
                "three 0-2 axes: correctness, groundedness, citation. Be strict.\n"
                "{format_instructions}",
            ),
            (
                "human",
                "Question: {question}\n\n"
                "Rubric: {rubric}\n\n"
                "Answer: {answer}\n\n"
                "Cited source ids: {cited_ids}",
            ),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | judge_llm | parser
    return await chain.ainvoke(
        {
            "question": query.query,
            "rubric": query.rubric,
            "answer": answer,
            "cited_ids": ", ".join(cited_ids),
        }
    )
