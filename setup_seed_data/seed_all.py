#!/usr/bin/env python3
"""
Seed all databases with Acme Corp data.

This script:
1. Creates PostgreSQL tables and loads sample data
2. Generates embeddings for documents using OpenAI
3. Stores documents with embeddings in MongoDB
4. Validates MCP fixtures are present

Usage:
    uv run python seed_all.py
"""

import json
import os
import sys
import traceback
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
except ImportError:
    print("❌ python-dotenv not installed. Run: uv sync")
    sys.exit(1)

# Load environment from setup_environment/.env
env_path = Path(__file__).parent.parent / "setup_environment" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"⚠️  No .env file found at {env_path}")
    print("   Copy env.example to .env and configure it first.")


def seed_postgres():
    """Create tables and load seed data into PostgreSQL."""
    print("\n📊 Seeding PostgreSQL...")

    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Run: uv sync")
        return False

    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "acme"),
            password=os.getenv("POSTGRES_PASSWORD", "acme"),
            database=os.getenv("POSTGRES_DB", "acme"),
        )
        cursor = conn.cursor()

        # Read and execute schema
        schema_path = Path(__file__).parent / "postgres" / "schema.sql"
        with open(schema_path) as f:
            cursor.execute(f.read())
        conn.commit()
        print("   ✓ Schema created")

        # Read and execute seed data
        seed_path = Path(__file__).parent / "postgres" / "seed_data.sql"
        with open(seed_path) as f:
            cursor.execute(f.read())
        conn.commit()
        print("   ✓ Seed data loaded")

        # Verify counts
        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM refunds")
        refund_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM employees")
        employee_count = cursor.fetchone()[0]

        print(
            f"   ✓ Loaded: {customer_count} customers, {refund_count} refunds, {employee_count} employees"
        )

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"❌ PostgreSQL seeding failed: {e}")
        print("   Make sure Docker is running: docker compose up -d")
        return False


def seed_mongodb():
    """Generate embeddings and load documents into MongoDB."""
    print("\n📚 Seeding MongoDB with documents...")

    try:
        from openai import OpenAI
        from pymongo import MongoClient
    except ImportError as e:
        print(f"❌ Missing dependency: {e}. Run: uv sync")
        return False

    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "sk-your-key-here":
        print("❌ OPENAI_API_KEY not configured in .env")
        return False

    try:
        # Connect to MongoDB
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        client = MongoClient(uri)
        db = client[os.getenv("MONGODB_DB", "acme")]

        # Clear existing documents
        db.documents.delete_many({})

        # Initialize OpenAI client
        openai_client = OpenAI(api_key=api_key)
        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

        # Find all markdown documents
        docs_path = Path(__file__).parent / "documents"
        documents = []

        for md_file in docs_path.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            category = md_file.parent.name  # policies, engineering, product

            documents.append(
                {
                    "filename": md_file.name,
                    "category": category,
                    "content": content,
                    "path": str(md_file.relative_to(docs_path)),
                }
            )

        print(f"   Found {len(documents)} documents")

        # Generate embeddings and insert
        for i, doc in enumerate(documents, 1):
            print(f"   Embedding {i}/{len(documents)}: {doc['filename']}...", end=" ")

            # Generate embedding
            response = openai_client.embeddings.create(
                input=doc["content"],
                model=embedding_model,
            )
            embedding = response.data[0].embedding

            # Insert into MongoDB
            db.documents.insert_one(
                {
                    "filename": doc["filename"],
                    "category": doc["category"],
                    "path": doc["path"],
                    "content": doc["content"],
                    "embedding": embedding,
                }
            )
            print("✓")

        # Create vector search index (note: requires Atlas for actual vector search)
        # For local MongoDB, we'll create a regular index
        db.documents.create_index([("category", 1)])
        db.documents.create_index([("filename", 1)])

        print(f"   ✓ Loaded {len(documents)} documents with embeddings")

        client.close()
        return True

    except Exception as e:
        print(traceback.format_exc())
        print(f"❌ MongoDB seeding failed: {e}")
        return False


def verify_mcp_fixtures():
    """Verify MCP fixture files are present and valid."""
    print("\n🔧 Verifying MCP fixtures...")

    fixtures_path = Path(__file__).parent / "mcp_fixtures"

    # Check Jira fixtures
    jira_path = fixtures_path / "jira_tickets.json"
    if jira_path.exists():
        with open(jira_path) as f:
            jira_data = json.load(f)
        ticket_count = len(jira_data.get("tickets", []))
        print(f"   ✓ Jira fixtures: {ticket_count} tickets")
    else:
        print(f"❌ Missing: {jira_path}")
        return False

    # Check Slack fixtures
    slack_path = fixtures_path / "slack_messages.json"
    if slack_path.exists():
        with open(slack_path) as f:
            slack_data = json.load(f)
        message_count = sum(
            len(m.get("thread", [])) for m in slack_data.get("messages", [])
        )
        print(f"   ✓ Slack fixtures: {message_count} messages")
    else:
        print(f"❌ Missing: {slack_path}")
        return False

    return True


def main():
    print("=" * 50)
    print("🌱 Acme Corp Data Seeding")
    print("=" * 50)

    results = []

    # Seed PostgreSQL
    results.append(("PostgreSQL", seed_postgres()))

    # Seed MongoDB
    results.append(("MongoDB", seed_mongodb()))

    # Verify MCP fixtures
    results.append(("MCP Fixtures", verify_mcp_fixtures()))

    # Summary
    print("\n" + "=" * 50)
    print("📋 Summary")
    print("=" * 50)

    all_passed = True
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"   {status} {name}")
        if not success:
            all_passed = False

    print()
    if all_passed:
        print("✅ All data seeded successfully!")
        print()
        print("Next step: run your first eval")
        print("   uv run python stage_1_golden_sets/evaluator.py")
        return 0
    else:
        print("❌ Some seeding steps failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
