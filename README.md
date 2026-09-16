# 🎯 Ask Acme - Production Evals Cookbook

> Learn how to build production-ready AI evaluations through 5 progressive stages, using a realistic knowledge base agent as the teaching example.

## What Is This?

A **hands-on tutorial** for evaluating AI systems properly. Instead of toy examples, you'll work with a realistic system: **Ask Acme** — a LangGraph agent that answers questions about a company by searching across documents, databases, and collaboration tools.

```
         "What's our refund policy and how many refunds last quarter?"
                                    │
                                    ▼
                          ┌─────────────────┐
                          │    ASK ACME     │
                          │   (LangGraph)   │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       ┌────────────┐       ┌────────────┐       ┌────────────┐
       │   Vector   │       │    SQL     │       │    MCP     │
       │   Search   │       │   Agent    │       │   Tools    │
       │ (MongoDB)  │       │ (Postgres) │       │(Jira/Slack)│
       └────────────┘       └────────────┘       └────────────┘
```

---

## Setup

**This is the only setup doc.** Run every command from the repo root — all scripts resolve their own paths, so there's no need to `cd` between folders.

**Prerequisites:** Python 3.11–3.13 · Docker · [uv](https://docs.astral.sh/uv/) · an OpenAI API key

```bash
# 1. Start the databases (Docker Desktop must be running first)
docker compose -f setup_environment/docker-compose.yml up -d postgres mongodb

# 2. Install dependencies
uv sync

# 3. Add your OpenAI key
cp setup_environment/env.example setup_environment/.env
#    then edit setup_environment/.env and set OPENAI_API_KEY=sk-...

# 4. Verify (checks both databases, your API key, and deps)
uv run python setup_environment/verify_setup.py

# 5. Load Acme Corp's data
uv run python setup_seed_data/seed_all.py
```

Then run your first eval:

```bash
uv run python stage_1_golden_sets/evaluator.py
```

Expected: `Total: 15/15 passed (100.0%)`

To explore the agent interactively instead: `uv run jupyter notebook setup_agent/demo.ipynb`

### Connection details

| Service | Host port | Credentials |
|---------|-----------|-------------|
| PostgreSQL | 5432 | user `acme` / password `acme` / db `acme` |
| MongoDB | 27017 | no auth |

### Stopping

```bash
docker compose -f setup_environment/docker-compose.yml down     # stop
docker compose -f setup_environment/docker-compose.yml down -v  # stop + wipe data (re-run step 5 after)
```

### Troubleshooting

**"Cannot connect to the Docker daemon"** — Docker Desktop isn't running. Start it, wait for the whale icon to settle, then retry step 1.

**"Bind for 0.0.0.0:5432 failed: port is already allocated"** — something else on your machine already owns Postgres's port, usually a local Postgres install or another project's container. Stop it (`docker stop <name>`, or `brew services stop postgresql`), or change the host port in `setup_environment/docker-compose.yml` to `"5433:5432"` and set `POSTGRES_PORT=5433` in `setup_environment/.env` to match — both must agree.

**`FATAL: role "acme" does not exist`** — you're reaching a *different* Postgres. A native install (Homebrew, Postgres.app) binds the specific address `127.0.0.1:5432`, while Docker binds the wildcard `*:5432`; the specific bind wins for `localhost`, so Docker starts without ever reporting a conflict and your queries silently hit the wrong server. Check with `lsof -nP -iTCP:5432 -sTCP:LISTEN` — if you see a `postgres` process alongside `com.docke`, stop it:
```bash
brew services stop postgresql@16    # restart later with: brew services start postgresql@16
```

**Postgres reports "healthy" but the connection is refused** — you have an `acme-postgres` container created under an older port mapping. `docker compose up` only *starts* existing containers; it never re-applies ports. Recreate it (your data lives in a named volume and survives):
```bash
docker compose -f setup_environment/docker-compose.yml up -d --force-recreate postgres
docker port acme-postgres   # should print 5432/tcp -> 0.0.0.0:5432
```

**"Bind for 0.0.0.0:8888 failed: port is already allocated"** — harmless. That's the optional `app` Jupyter container, which the setup above skips by naming `postgres mongodb` explicitly.

**"Command not found: uv"** — `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

**"Invalid API key"** — check for stray spaces or quotes around the key in `setup_environment/.env`.

### Optional: run everything in Docker

If you'd rather not install Python locally, `docker compose -f setup_environment/docker-compose.yml up -d` also starts a Jupyter container on port 8888, then prefix commands with `docker compose -f setup_environment/docker-compose.yml exec app`.

### Optional: LangSmith tracing

Add to `setup_environment/.env`, then view traces at [smith.langchain.com](https://smith.langchain.com):

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-key-here
LANGCHAIN_PROJECT=ask-acme
```

---

## The Evaluation Stages

Work through these in order. Each folder has a README covering the concepts and a `walkthrough.ipynb` with exercises.

| Stage | Folder | What You'll Learn |
|-------|--------|-------------------|
| 1 | `stage_1_golden_sets/` | Curated input/output pairs — baseline correctness |
| 2 | `stage_2_labeled_scenarios/` | Categorized test cases — coverage mapping |
| 3 | `stage_3_replay_harnesses/` | Record/replay — reproducibility + rich metrics |
| 4 | `stage_4_rubrics/` | Multi-dimensional scoring with LLM-as-judge |
| 5 | `stage_5_experiments/` | Compare agent configurations with data |

Every stage runs the same way:

```bash
uv run python stage_1_golden_sets/evaluator.py
```

## How the Agent Is Built

The `setup_*/` folders are reference material — you don't need to read them to run the evals.

| File | Purpose |
|------|---------|
| `setup_agent/orchestrator.py` | LangGraph agent; exports `ask_acme` and `ask_acme_with_trace` |
| `setup_agent/vector_search.py` | Embedding search over MongoDB documents |
| `setup_agent/sql_agent.py` | Natural language → SQL against Postgres |
| `setup_agent/mcp_tools.py` | Jira and Slack fixture search |
| `setup_agent/config.py` | Loads `setup_environment/.env` |
| `setup_seed_data/seed_all.py` | Loads all Acme Corp data |

The evaluators import `ask_acme_with_trace` directly — it returns both the response and the tool calls the agent made, which is what the checks assert against.

## The Fictional Company

All data is synthetic. **Acme Corp** is a fictional B2B project management company: 200 employees, 2,400+ customers, $18M ARR, with 3 years of business data, 8 internal documents, Jira tickets, and Slack messages.

## License

MIT
