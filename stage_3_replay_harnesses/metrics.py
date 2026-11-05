"""
Evaluation metrics for Ask Acme.

Implements retrieval and generation metrics for comprehensive evaluation.
"""

import sys
from pathlib import Path
from typing import Any

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "setup_agent"))

from langchain_core.prompts import ChatPromptTemplate

from config import chat_model


# =============================================================================
# RETRIEVAL METRICS
# =============================================================================

def precision(retrieved: list[str], relevant: list[str]) -> float:
    """
    Calculate retrieval precision.
    
    Precision = |relevant ∩ retrieved| / |retrieved|
    
    Args:
        retrieved: List of retrieved document names/IDs
        relevant: List of relevant document names/IDs (ground truth)
        
    Returns:
        Precision score between 0 and 1
    """
    if not retrieved:
        return 0.0
    
    retrieved_set = set(s.lower() for s in retrieved)
    relevant_set = set(s.lower() for s in relevant)
    
    relevant_retrieved = retrieved_set & relevant_set
    return len(relevant_retrieved) / len(retrieved_set)


def recall(retrieved: list[str], relevant: list[str]) -> float:
    """
    Calculate retrieval recall.
    
    Recall = |relevant ∩ retrieved| / |relevant|
    
    Args:
        retrieved: List of retrieved document names/IDs
        relevant: List of relevant document names/IDs (ground truth)
        
    Returns:
        Recall score between 0 and 1
    """
    if not relevant:
        return 1.0  # If no relevant docs, perfect recall by default
    
    retrieved_set = set(s.lower() for s in retrieved)
    relevant_set = set(s.lower() for s in relevant)
    
    relevant_retrieved = retrieved_set & relevant_set
    return len(relevant_retrieved) / len(relevant_set)


def f1_score(retrieved: list[str], relevant: list[str]) -> float:
    """
    Calculate F1 score (harmonic mean of precision and recall).
    
    Args:
        retrieved: List of retrieved document names/IDs
        relevant: List of relevant document names/IDs (ground truth)
        
    Returns:
        F1 score between 0 and 1
    """
    p = precision(retrieved, relevant)
    r = recall(retrieved, relevant)
    
    if p + r == 0:
        return 0.0
    
    return 2 * (p * r) / (p + r)


def mrr(retrieved: list[str], relevant: list[str]) -> float:
    """
    Calculate Mean Reciprocal Rank.
    
    MRR = 1 / rank of first relevant result
    
    Args:
        retrieved: Ordered list of retrieved document names/IDs
        relevant: List of relevant document names/IDs (ground truth)
        
    Returns:
        MRR score between 0 and 1
    """
    if not retrieved or not relevant:
        return 0.0
    
    relevant_set = set(s.lower() for s in relevant)
    
    for i, doc in enumerate(retrieved, 1):
        if doc.lower() in relevant_set:
            return 1.0 / i
    
    return 0.0


# =============================================================================
# GENERATION METRICS (LLM-as-Judge)
# =============================================================================

def get_judge_llm():
    """Get LLM for judging."""
    return chat_model()


GROUNDEDNESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are evaluating whether a response is grounded in the provided sources.

For each claim in the response, determine if it is supported by the sources.

Sources:
{sources}

Response to evaluate:
{response}

Instructions:
1. List each factual claim in the response
2. For each claim, mark it as GROUNDED (supported by sources) or UNGROUNDED (not in sources)
3. Calculate the percentage of grounded claims

Output format:
CLAIMS:
1. [claim] - GROUNDED/UNGROUNDED
2. [claim] - GROUNDED/UNGROUNDED
...

GROUNDED_COUNT: X
TOTAL_COUNT: Y
SCORE: X/Y = Z.ZZ"""),
    ("human", "Evaluate the groundedness of the response."),
])


def groundedness(response: str, sources: list[str]) -> dict[str, Any]:
    """
    Evaluate how grounded the response is in the provided sources.
    
    Uses LLM-as-judge to check each claim against sources.
    
    Args:
        response: The generated response
        sources: List of source document contents
        
    Returns:
        Dict with score and details
    """
    if not response or not sources:
        return {"score": 0.0, "details": "No response or sources to evaluate"}
    
    llm = get_judge_llm()
    
    sources_text = "\n\n---\n\n".join(sources[:3])  # Limit to 3 sources
    
    result = llm.invoke(
        GROUNDEDNESS_PROMPT.format_messages(
            sources=sources_text,
            response=response
        )
    )
    
    # Parse the score from the response
    content = str(result.text)
    score = 0.0
    
    try:
        # Look for SCORE line
        for line in content.split("\n"):
            if "SCORE:" in line:
                # Extract the decimal at the end
                parts = line.split("=")
                if len(parts) > 1:
                    score = float(parts[-1].strip())
                    break
    except (ValueError, IndexError):
        # If parsing fails, estimate from GROUNDED/UNGROUNDED counts
        grounded = content.lower().count("grounded") - content.lower().count("ungrounded")
        total = content.lower().count("grounded")
        if total > 0:
            score = max(0, grounded) / total
    
    return {
        "score": min(1.0, max(0.0, score)),
        "details": content,
    }


FAITHFULNESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are evaluating whether a response contains any hallucinations or made-up information.

A response is FAITHFUL if every claim can be traced back to the sources.
A response is UNFAITHFUL if it contains information not present in sources.

Sources:
{sources}

Response to evaluate:
{response}

Instructions:
1. Identify any claims that are NOT supported by the sources
2. Rate the response: FAITHFUL (no hallucinations) or UNFAITHFUL (contains hallucinations)
3. List any hallucinated claims

Output format:
VERDICT: FAITHFUL or UNFAITHFUL
HALLUCINATIONS: [list any made-up claims, or "None"]
SCORE: 1.0 (faithful) or 0.0 (unfaithful)"""),
    ("human", "Evaluate the faithfulness of the response."),
])


def faithfulness(response: str, sources: list[str]) -> dict[str, Any]:
    """
    Evaluate whether the response is faithful to sources (no hallucination).
    
    Args:
        response: The generated response
        sources: List of source document contents
        
    Returns:
        Dict with score and details
    """
    if not response or not sources:
        return {"score": 0.0, "details": "No response or sources to evaluate"}
    
    llm = get_judge_llm()
    
    sources_text = "\n\n---\n\n".join(sources[:3])
    
    result = llm.invoke(
        FAITHFULNESS_PROMPT.format_messages(
            sources=sources_text,
            response=response
        )
    )
    
    content = str(result.text)
    
    # Parse verdict
    score = 1.0 if "FAITHFUL" in content.upper() and "UNFAITHFUL" not in content.upper() else 0.0
    
    # Try to parse explicit score
    for line in content.split("\n"):
        if "SCORE:" in line:
            try:
                score = float(line.split(":")[-1].strip())
            except ValueError:
                pass
    
    return {
        "score": score,
        "details": content,
    }


RELEVANCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are evaluating whether a response is relevant to the question asked.

Question:
{question}

Response:
{response}

Rate the relevance on a scale of 1-5:
1 - Completely irrelevant, doesn't address the question at all
2 - Mostly irrelevant, barely touches on the topic
3 - Partially relevant, addresses some aspects but misses key points
4 - Mostly relevant, addresses the main question with minor gaps
5 - Fully relevant, directly and completely addresses the question

Output format:
SCORE: [1-5]
REASONING: [brief explanation]"""),
    ("human", "Rate the relevance of the response."),
])


def relevance(question: str, response: str) -> dict[str, Any]:
    """
    Evaluate how relevant the response is to the question.
    
    Args:
        question: The original question
        response: The generated response
        
    Returns:
        Dict with score (1-5) and reasoning
    """
    if not question or not response:
        return {"score": 1, "reasoning": "No question or response to evaluate"}
    
    llm = get_judge_llm()
    
    result = llm.invoke(
        RELEVANCE_PROMPT.format_messages(
            question=question,
            response=response
        )
    )
    
    content = str(result.text)
    score = 3  # Default middle score
    reasoning = content
    
    # Parse score
    for line in content.split("\n"):
        if "SCORE:" in line:
            try:
                score = int(line.split(":")[-1].strip())
                score = max(1, min(5, score))
            except ValueError:
                pass
        if "REASONING:" in line:
            reasoning = line.split(":", 1)[-1].strip()
    
    return {
        "score": score,
        "reasoning": reasoning,
    }


# =============================================================================
# TOOL METRICS
# =============================================================================

def tool_accuracy(expected_tools: list[str], actual_tools: list[str]) -> float:
    """
    Calculate tool selection accuracy.
    
    Args:
        expected_tools: Tools that should have been called
        actual_tools: Tools that were actually called
        
    Returns:
        Accuracy score between 0 and 1
    """
    if not expected_tools:
        return 1.0 if not actual_tools else 0.0
    
    expected_set = set(expected_tools)
    actual_set = set(actual_tools)
    
    # Perfect match = 1.0
    if expected_set == actual_set:
        return 1.0
    
    # Partial credit: Jaccard similarity
    intersection = len(expected_set & actual_set)
    union = len(expected_set | actual_set)
    
    return intersection / union if union > 0 else 0.0


def tool_efficiency(expected_tools: list[str], actual_tools: list[str]) -> float:
    """
    Calculate tool efficiency (penalize unnecessary calls).
    
    Args:
        expected_tools: Tools that should have been called
        actual_tools: Tools that were actually called
        
    Returns:
        Efficiency score between 0 and 1
    """
    if not actual_tools:
        return 1.0 if not expected_tools else 0.0
    
    expected_set = set(expected_tools)
    actual_set = set(actual_tools)
    
    unnecessary = len(actual_set - expected_set)
    
    # Penalize each unnecessary call
    return max(0.0, 1.0 - (unnecessary * 0.25))


# =============================================================================
# AGGREGATE METRICS
# =============================================================================

def evaluate_all(
    question: str,
    response: str,
    retrieved_sources: list[str],
    source_contents: list[str],
    relevant_sources: list[str],
    expected_tools: list[str],
    actual_tools: list[str],
) -> dict[str, Any]:
    """
    Run all evaluation metrics.
    
    Args:
        question: The original question
        response: The generated response
        retrieved_sources: Names of retrieved source documents
        source_contents: Actual content of retrieved sources
        relevant_sources: Ground truth relevant sources
        expected_tools: Expected tools to be called
        actual_tools: Actually called tools
        
    Returns:
        Dict with all metric scores
    """
    results = {
        "retrieval": {
            "precision": precision(retrieved_sources, relevant_sources),
            "recall": recall(retrieved_sources, relevant_sources),
            "f1": f1_score(retrieved_sources, relevant_sources),
            "mrr": mrr(retrieved_sources, relevant_sources),
        },
        "generation": {
            "groundedness": groundedness(response, source_contents),
            "faithfulness": faithfulness(response, source_contents),
            "relevance": relevance(question, response),
        },
        "tools": {
            "accuracy": tool_accuracy(expected_tools, actual_tools),
            "efficiency": tool_efficiency(expected_tools, actual_tools),
        },
    }
    
    # Calculate overall score
    retrieval_score = (
        results["retrieval"]["precision"] + 
        results["retrieval"]["recall"]
    ) / 2
    
    generation_score = (
        results["generation"]["groundedness"]["score"] +
        results["generation"]["faithfulness"]["score"] +
        (results["generation"]["relevance"]["score"] / 5)
    ) / 3
    
    tool_score = (
        results["tools"]["accuracy"] +
        results["tools"]["efficiency"]
    ) / 2
    
    results["overall"] = (retrieval_score + generation_score + tool_score) / 3
    
    return results
