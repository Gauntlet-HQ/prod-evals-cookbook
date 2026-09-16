#!/usr/bin/env python3
"""
Verify that the development environment is set up correctly.
Run this after completing the setup steps in README.md.
"""

import os
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print("⚠ No .env file found. Copy env.example to .env and configure it.")
        print("  cp env.example .env")
        print()
except ImportError:
    print("⚠ python-dotenv not installed. Run: uv sync")
    sys.exit(1)


def check_postgres() -> bool:
    """Check PostgreSQL connection."""
    try:
        import psycopg2
        
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "acme"),
            password=os.getenv("POSTGRES_PASSWORD", "acme"),
            database=os.getenv("POSTGRES_DB", "acme"),
            connect_timeout=5,
        )
        conn.close()
        print("✓ PostgreSQL connection successful")
        return True
    except ImportError:
        print("✗ psycopg2 not installed. Run: uv sync")
        return False
    except Exception as e:
        print(f"✗ PostgreSQL connection failed: {e}")
        print("  Make sure Docker is running: docker compose up -d")
        return False


def check_mongodb() -> bool:
    """Check MongoDB connection."""
    try:
        from pymongo import MongoClient
        from pymongo.errors import ServerSelectionTimeoutError
        
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Force a connection attempt
        client.admin.command("ping")
        client.close()
        print("✓ MongoDB connection successful")
        return True
    except ImportError:
        print("✗ pymongo not installed. Run: uv sync")
        return False
    except ServerSelectionTimeoutError:
        print("✗ MongoDB connection failed: server not reachable")
        print("  Make sure Docker is running: docker compose up -d")
        return False
    except Exception as e:
        print(f"✗ MongoDB connection failed: {e}")
        return False


def check_openai_key() -> bool:
    """Check OpenAI API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    
    if not api_key:
        print("✗ OPENAI_API_KEY not set in .env file")
        return False
    
    if api_key == "sk-your-key-here":
        print("✗ OPENAI_API_KEY is still the placeholder value")
        print("  Edit .env and add your real API key")
        return False
    
    if not api_key.startswith("sk-"):
        print("⚠ OPENAI_API_KEY doesn't look like a valid key (should start with 'sk-')")
        return False
    
    print("✓ OpenAI API key configured")
    return True


def check_dependencies() -> bool:
    """Check that key dependencies are installed."""
    missing = []
    
    packages = [
        ("langchain", "langchain"),
        ("langchain_openai", "langchain-openai"),
        ("langgraph", "langgraph"),
        ("pydantic", "pydantic"),
        ("yaml", "pyyaml"),
    ]
    
    for module_name, package_name in packages:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    
    if missing:
        print(f"✗ Missing packages: {', '.join(missing)}")
        print("  Run: uv sync")
        return False
    
    print("✓ All dependencies installed")
    return True


def main():
    print("=" * 50)
    print("Ask Acme - Environment Verification")
    print("=" * 50)
    print()
    
    results = [
        check_postgres(),
        check_mongodb(),
        check_openai_key(),
        check_dependencies(),
    ]
    
    print()
    print("=" * 50)
    
    if all(results):
        print("✓ All checks passed!")
        print()
        print("Next step: load the seed data")
        print("  uv run python setup_seed_data/seed_all.py")
        return 0
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
