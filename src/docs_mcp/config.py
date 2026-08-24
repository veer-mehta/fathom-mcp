from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://docs_mcp:docs_mcp@localhost:5432/docs_mcp"
    embedding_provider: str = "openai"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    local_embedding_max_tokens: int = 1024
    local_embedding_device: str = "auto"
    crawl_max_depth: int = 2
    crawl_max_pages: int = 30
    crawl_delay: float = 0.5
    user_agent: str = "docs-mcp-bot/0.1 (documentation indexer)"
    mcp_transport: str = "stdio"
    api_host: str = "127.0.0.1"
    api_port: int = 8000


settings = Settings()
