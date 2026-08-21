import json
import logging
from datetime import datetime

from mcp.server.mcpserver import MCPServer

from docs_mcp.config import settings
from docs_mcp.pipeline import ingest_documentation
from docs_mcp.storage.db import Database

logger = logging.getLogger(__name__)

mcp = MCPServer("docs-rag")
db = Database(settings.database_url)


def _source_pattern(name: str | None, version: str | None) -> str | None:
    if name and version:
        return f"{name}@{version}"
    if name:
        return f"{name}@%"
    if version:
        return f"%@{version}"
    return None


@mcp.tool()
async def add_documentation(
    name: str, version: str, base_url: str, max_depth: int = 2, max_pages: int = 30
) -> str:
    """Crawl a framework/library documentation site and index it for semantic search.

    Args:
        name: Short identifier for the framework, e.g. "react".
        version: Version string, e.g. "18.3" or "latest".
        base_url: Entry point URL of the documentation site.
        max_depth: How many link hops to follow from base_url.
        max_pages: Hard cap on the number of pages crawled.
    """
    result = await ingest_documentation(
        db, name, version, base_url, max_depth=max_depth, max_pages=max_pages
    )
    return json.dumps(result)


@mcp.tool()
async def search_documentation(
    query: str, name: str | None = None, version: str | None = None, k: int = 5
) -> str:
    """Semantic search over indexed documentation.

    Returns the most relevant markdown chunks with their source URL and
    heading path. Use add_documentation first if nothing is indexed yet.

    Args:
        query: What to look for, e.g. "how to define a loader".
        name: Optional framework name filter, e.g. "react".
        version: Optional version filter, e.g. "18.3".
        k: Number of chunks to return (1-20).
    """
    from docs_mcp.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    await db.ensure_schema(provider.dimensions)
    vectors = await provider.embed([query])
    hits = await db.search(
        vectors[0], _source_pattern(name, version), max(1, min(k, 20))
    )
    if not hits:
        return "No matching documentation found. Call add_documentation first."
    blocks = []
    for hit in hits:
        header = hit.title or hit.url
        crumb = " > ".join(hit.heading_path)
        if crumb:
            header += f" — {crumb}"
        blocks.append(
            f"### [{header}]({hit.url}) (relevance {hit.similarity:.2f})\n\n{hit.content}"
        )
    return "\n\n---\n\n".join(blocks)


@mcp.tool()
async def list_sources() -> str:
    """List all indexed documentation sources with page and chunk counts."""
    rows = await db.list_sources()
    if not rows:
        return "No sources indexed yet."
    lines = []
    for row in rows:
        updated = row["updated_at"]
        if isinstance(updated, datetime):
            updated = updated.isoformat()
        lines.append(
            f"- {row['source_id']}: {row['pages']} pages, {row['chunks']} chunks "
            f"(updated {updated})"
        )
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
