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

Three ways to use it — same pipeline, different front doors.

### 1. MCP server (for AI clients)

```bash
.venv/bin/docs-mcp-server            # stdio transport
```

Register with Claude Desktop / Cursor / opencode:

```json
{
  "mcpServers": {
    "docs-rag": {
      "command": "/absolute/path/to/mcp-project/.venv/bin/docs-mcp-server"
    }
  }
}
```

MCP over HTTP instead of stdio: set `MCP_TRANSPORT=streamable-http` in `.env` and run the same command (endpoint: `http://127.0.0.1:8000/mcp`).

### 2. Web UI

```bash
.venv/bin/docs-mcp-api               # then open http://127.0.0.1:8000
```

Browser UI for searching indexed docs, managing sources, and ingesting new ones.
The **backend toggle** at the top switches every panel between:

- `RAG — direct pipeline access`: REST endpoints calling the library directly
- `MCP — tool calls through docs-mcp server`: the same operations executed as real
  MCP tool calls (`search_documentation`, `add_documentation`, …) against a
  `docs-mcp-server` subprocess managed by the API server

### 3. REST API (same server as the web UI)

```bash
# blocking (returns final counts)
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
     -d '{"name":"pydantic","version":"2.13","base_url":"https://docs.pydantic.dev/latest/","max_depth":1,"max_pages":6}'

# background (202 immediately, poll for progress — use this for large sites)
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
     -d '{"name":"pydantic","version":"2.13","base_url":"https://docs.pydantic.dev/latest/","background":true}'
curl localhost:8000/jobs/<job_id>   # live counters; status done|failed carries result
curl localhost:8000/jobs            # recent jobs

curl 'localhost:8000/search?q=how+do+I+install&k=3&mode=hybrid'
curl localhost:8000/sources
curl -X DELETE localhost:8000/sources/pydantic@2.13
```

### 4. Plain Python library

```python
import asyncio
from docs_mcp.pipeline import ingest_documentation
from docs_mcp.embeddings import get_embedding_provider
from docs_mcp.storage.db import Database

async def main():
    db, provider = Database(DSN), get_embedding_provider()
    await db.ensure_schema(provider.dimensions)
    await ingest_documentation(db, "pydantic", "2.13", "https://docs.pydantic.dev/latest/")
    vec = (await provider.embed(["how do I install"]))[0]
    for hit in await db.search(vec, k=3):
        print(hit.similarity, hit.url)

asyncio.run(main())
```

Runnable version: `.venv/bin/python scripts/demo.py`

### Tools / endpoints reference

| MCP tool | REST | Description |
| --- | --- | --- |
| `add_documentation(name, version, base_url, max_depth=2, max_pages=30, background=false, prune_missing=false)` | `POST /ingest` (`"background": true` → 202) | Crawl a docs site (same-domain, depth/page limited), index as `{name}@{version}`. `background=true` returns a job id immediately. Re-ingesting is **incremental**: unchanged pages (sha256 of extracted markdown) skip chunking/embedding. `prune_missing=true` also deletes indexed pages the crawl didn't visit — only use with caps that cover the whole site |
| `get_ingest_status(job_id)` | `GET /jobs/{job_id}` | Progress of a background ingest (live page/chunk counters); `done` includes the final result |
| — | `GET /jobs` | Recent background jobs (newest first) |
| `search_documentation(query, name?, version?, k=5, mode="hybrid")` | `GET /search` | Semantic search; returns markdown chunks with source URL + heading path. `mode` = `hybrid` (default; vector + keyword fused via Reciprocal Rank Fusion), `vector`, or `keyword`. REST adds it as the `mode` query param |
| *any tool* | `GET/POST /mcp/search` · `/mcp/sources` · `/mcp/ingest` · `/mcp/jobs/{id}` | Same operations routed through a real MCP session: the API server spawns `docs-mcp-server` over stdio and proxies requests as tool calls (`McpBridge`). The web UI's backend toggle switches between direct RAG and this MCP path |
| `list_sources()` | `GET /sources` | List indexed sources with page/chunk counts |
| — | `DELETE /sources/{source_id}` | Remove an indexed source |

## Embedding providers

Set `EMBEDDING_PROVIDER` in `.env`:

- `openai` — `text-embedding-3-small` (needs `OPENAI_API_KEY`)
- `local` — sentence-transformers models, offline (install with `pip install -e ".[local]"`). Recommended: `BAAI/bge-m3` (1024-dim, multilingual, runs well on an RTX GPU); lighter CPU option: `BAAI/bge-base-en-v1.5`. Knobs: `LOCAL_EMBEDDING_MAX_TOKENS` (default 1024 — caps activation memory), `LOCAL_EMBEDDING_DEVICE` = `auto` (default; picks CUDA only if ≥4 GiB free, else CPU) | `cuda` | `cpu`. Batches that OOM the GPU at encode time automatically retry on CPU
- `hash` — deterministic fake vectors, dev/testing only, no semantic quality

Note: pgvector columns are fixed-width, so switching between providers with different dimensions requires `DROP TABLE documents;` and re-ingesting.

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
- Background jobs live in process memory: job history is lost on restart, and a background job submitted through one server (e.g. stdio MCP) can't be polled from another (e.g. REST) — except when submitted via the web UI's MCP backend, whose bridge session stays connected to that same server process
- Source deletion is only available on the RAG backend (no MCP tool for it yet)
- Single embedding dimension per database (switching providers requires re-ingestion)
- Incremental re-crawl hashes are per-page over the extracted markdown; rows predating the feature are backfilled on first re-ingest (one full re-embed), and `prune_missing` with capped crawls will delete unvisited pages by design
