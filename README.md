# docs-mcp

An MCP (Model Context Protocol) server that crawls framework/library documentation sites, converts pages to markdown, chunks and embeds them into Postgres (pgvector), and exposes semantic search over the indexed docs to any MCP client.

## Architecture

```
MCP client ──stdio──▶ FastMCP server
                        │ add_documentation() ──▶ scrapy+playwright subprocess (JSONL)
                        │                            └─▶ trafilatura → markdown → chunker → embeddings → Postgres/pgvector
                        │ search_documentation() ──▶ embed query ──▶ cosine top-k ──▶ cited markdown chunks
                        └ list_sources()
```

## Setup

```bash
docker compose up -d                 # Postgres 16 + pgvector on localhost:5432
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env                 # set OPENAI_API_KEY (or EMBEDDING_PROVIDER=hash for testing)
.venv/bin/playwright install chromium
```

## Run

```bash
.venv/bin/docs-mcp-server            # stdio MCP server
```

### Register with an MCP client

Claude Desktop / Cursor / opencode config:

```json
{
  "mcpServers": {
    "docs-rag": {
      "command": "/absolute/path/to/mcp-project/.venv/bin/docs-mcp-server"
    }
  }
}
```

## Tools

| Tool | Description |
| --- | --- |
| `add_documentation(name, version, base_url, max_depth=2, max_pages=30)` | Crawl a docs site (same-domain, depth/page limited), index it as `{name}@{version}` |
| `search_documentation(query, name?, version?, k=5)` | Semantic search; returns markdown chunks with source URL + heading path |
| `list_sources()` | List indexed sources with page/chunk counts |

## Embedding providers

Set `EMBEDDING_PROVIDER` in `.env`:

- `openai` — `text-embedding-3-small` (default, needs `OPENAI_API_KEY`)
- `local` — sentence-transformers MiniLM, offline (install with `pip install -e ".[local]"`, requires Python <3.14 for torch)
- `hash` — deterministic fake vectors, dev/testing only, no semantic quality

## Standalone crawler

```bash
.venv/bin/python -m docs_mcp.scraper.runner --url https://docs.example.com --depth 1 --max-pages 5 > pages.jsonl
```

## Tests

```bash
.venv/bin/pytest                     # unit tests
.venv/bin/pytest -m integration      # requires docker compose up
```

## Limitations (MVP)

- Query strings are stripped during crawling (some paginated docs may collapse)
- Ingestion runs synchronously inside the tool call; large sites need lower `max_pages`
- Single embedding dimension per database (switching providers requires re-ingestion)
