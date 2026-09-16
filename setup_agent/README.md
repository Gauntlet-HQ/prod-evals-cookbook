# The Ask Acme Agent

> **Setup instructions live in the [root README](../README.md).** This file is reference only.

**Ask Acme** is a LangGraph agent that routes questions to the right data source and synthesizes an answer. The evaluators import it directly — it is not a package you install.

```python
from orchestrator import ask_acme, ask_acme_with_trace

ask_acme("What's our remote work policy?")             # -> str
ask_acme_with_trace("What's our remote work policy?")  # -> {"response": str, "tool_calls": [...]}
```

Evals use `ask_acme_with_trace` because the checks assert on *which tools ran*, not just the text.

## Flow

```
User Query → ROUTER (picks tools) → [vector_search | sql_query | jira_search | slack_search] → SYNTHESIZER → Response
```

## Files

| File | Purpose |
|------|---------|
| `orchestrator.py` | LangGraph agent, system prompt, and both entry points |
| `vector_search.py` | Embeds the query, finds similar MongoDB documents |
| `sql_agent.py` | Natural language → SQL against Postgres |
| `mcp_tools.py` | Searches Jira and Slack fixtures |
| `config.py` | Loads `../setup_environment/.env` |
| `eval_checks.py` | Shared check helpers used by every stage's evaluator |
| `demo.ipynb` | Interactive notebook |

## Example Queries

| Tool exercised | Query |
|----------------|-------|
| `vector_search` | "What's our remote work policy?" |
| `sql_query` | "What's our MRR?" |
| `jira_search` | "What P0 bugs are open?" |
| `slack_search` | "What did engineering decide about notifications?" |
| multi-tool | "What's our refund policy and how many refunds last quarter?" |
