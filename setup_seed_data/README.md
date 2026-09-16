# Seed Data

> **Setup instructions live in the [root README](../README.md).** This file is reference only.

Loads the fictional Acme Corp dataset: `uv run python setup_seed_data/seed_all.py`

## What Gets Loaded

| Source | Data | Enables |
|--------|------|---------|
| **PostgreSQL** | 3 years of business data across 5 tables | `sql_query` |
| **MongoDB** | 8 documents with OpenAI embeddings | `vector_search` |
| **Fixtures** | 8 Jira tickets, 23 Slack messages | `jira_search`, `slack_search` |

Re-running `seed_all.py` is safe — it recreates the schema and re-embeds from scratch. Step 3 costs 8 OpenAI embedding calls.

## The Documents

| Policies | Engineering | Product |
|----------|-------------|---------|
| `remote_work_policy.md` | `incident_runbook.md` | `roadmap_2025.md` |
| `pto_policy.md` | `code_review_standards.md` | `pricing_strategy.md` |
| `refund_policy.md` | `oncall_handbook.md` | |

## Verifying

```bash
docker compose -f ../setup_environment/docker-compose.yml exec postgres \
  psql -U acme -d acme -c "SELECT COUNT(*) FROM customers;"

uv run python -c "from pymongo import MongoClient; \
  print(MongoClient('mongodb://localhost:27017').acme.documents.count_documents({}))"
```
