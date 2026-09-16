# Environment Setup

> **Setup instructions live in the [root README](../README.md).** This file is reference only.

## What Runs Here

| Component | Purpose | Host port |
|-----------|---------|-----------|
| **PostgreSQL** | Analytics database (customers, metrics, refunds) | 5432 |
| **MongoDB** | Document store with embeddings for vector search | 27017 |
| `app` (optional) | Jupyter container, for running without local Python | 8888 |

If port 5432 is already taken on your machine, change the host side of the mapping in `docker-compose.yml` (e.g. `"5433:5432"`) and set a matching `POSTGRES_PORT` in `.env` — the two must agree.

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Postgres, MongoDB, and the optional Jupyter app container |
| `env.example` | Template for `.env` — copy it and add your OpenAI key |
| `.env` | Your local config (gitignored); loaded by `setup_agent/config.py` |
| `verify_setup.py` | Checks both databases, your API key, and installed deps |
| `Dockerfile` | Builds the optional `app` container |

## Connecting Directly

```bash
docker compose -f docker-compose.yml exec postgres psql -U acme -d acme
docker compose -f docker-compose.yml exec mongodb mongosh
```

Or from any client: `localhost:5432` (user `acme` / password `acme` / db `acme`) and `mongodb://localhost:27017`.
