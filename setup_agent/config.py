"""
Configuration for Ask Acme agent.

Loads environment variables and provides typed configuration.
"""

import os
import re
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings


# Load environment from setup_environment/.env
_env_path = Path(__file__).parent.parent / "setup_environment" / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    # Force reasoning-model handling on/off; leave unset to infer from the model name
    openai_reasoning_model: bool | None = None

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "acme"
    postgres_password: str = "acme"
    postgres_db: str = "acme"
    
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "acme"
    
    # LangSmith (optional)
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "ask-acme"
    
    @property
    def postgres_connection_string(self) -> str:
        """PostgreSQL connection string."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience exports
settings = get_settings()


# o1/o3/o4..., gpt-5*, gpt-6* and later — excluding the "-chat" variants,
# which behave like classic chat models.
_REASONING_MODEL_RE = re.compile(r"^(o\d|gpt-(?:[5-9]|\d{2,}))", re.IGNORECASE)


def is_reasoning_model(model: str) -> bool:
    """Whether a model needs reasoning-model handling (see chat_model)."""
    if settings.openai_reasoning_model is not None and model == settings.openai_model:
        return settings.openai_reasoning_model
    return bool(_REASONING_MODEL_RE.match(model)) and "-chat" not in model.lower()


def chat_model(model: str | None = None, temperature: float = 0) -> ChatOpenAI:
    """Build a ChatOpenAI client that works for both classic and reasoning models.

    Reasoning models (e.g. gpt-6-luna) only accept the default temperature and
    reject function tools on /v1/chat/completions, so for those we drop the
    temperature and route through the Responses API. Their replies come back as
    content blocks, so read text with ``message.text`` rather than ``.content``.
    """
    model = model or settings.openai_model
    if is_reasoning_model(model):
        return ChatOpenAI(
            model=model,
            use_responses_api=True,
            openai_api_key=settings.openai_api_key,
        )
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=settings.openai_api_key,
    )
