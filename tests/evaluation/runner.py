"""Runners for retrieval-only and full-agent evaluation."""

from __future__ import annotations

from typing import Any

from backend.api.dependencies import get_driver, get_embedder
from backend.rag.retriever import GraphRAGRetriever
from tests.evaluation.models import AgentResult, JudgeVerdict, Query, RetrievalResult
from tests.evaluation.scoring import build_retrieval_result


def build_retriever(top_k: int = 8) -> GraphRAGRetriever:
    """Build a retriever wired to the configured Neo4j instance."""
    driver = get_driver()
    embedder = get_embedder()
    return GraphRAGRetriever(driver, embedder, top_k=top_k)


def run_retrieval_evaluation(
    queries: list[Query],
    *,
    top_k: int = 8,
) -> list[RetrievalResult]:
    """Run the retrieval-only pass over the golden set.

    Returns one ``RetrievalResult`` per query, containing recall@k and army
    presence flags.
    """
    retriever = build_retriever(top_k=top_k)
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


def _extract_cited_ids_from_tool_content(content: Any) -> list[str]:
    """Pull cited source ids out of a tool result payload.

    Handles both the Anthropic native list-of-blocks format and the legacy
    JSON-string format.
    """
    import json

    if isinstance(content, list):
        ids: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                try:
                    payload = json.loads(block.get("text", ""))
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
                    ids.extend(
                        src["id"]
                        for src in payload["sources"]
                        if isinstance(src, dict) and src.get("id")
                    )
        return ids

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
) -> list[AgentResult]:
    """Run the full agent + optional LLM-judge pass over the golden set.

    If ``judge_llm`` is not provided, the agent answer and citations are
    recorded but ``verdict`` is left as ``None``.
    """
    import os

    from langchain.agents import create_agent
    from langchain.messages import AIMessage, AnyMessage, HumanMessage
    from langgraph.types import Command

    from backend.api.dependencies import get_llm
    from backend.api.dependencies import get_rag_pipeline as _get_rag_pipeline
    from backend.rag.prompts.system_prompt import SYSTEM_PROMPT
    from backend.rag.tools import build_tools

    retriever = build_retriever(top_k=top_k)
    pipeline = _get_rag_pipeline()
    llm = get_llm()
    tools = build_tools(pipeline)
    agent = create_agent(llm, tools=tools, system_prompt=SYSTEM_PROMPT)
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
                cited_ids.extend(_extract_cited_ids_from_tool_content(msg.content))

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
