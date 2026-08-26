# docs-rag

Documentation RAG system: crawl a docs site → chunk + embed locally (HuggingFace)
→ store in Postgres+pgvector → semantic search via MCP server, REST API, and web UI.

## Commands

- Tests: `.venv/bin/pytest` (unit tests, no external services needed)
- API + web UI: `docs-mcp-api` → http://127.0.0.1:8000
- MCP server: `docs-mcp-server` (stdio)
- Crawler CLI: `docs-mcp-crawl --url <url>`

Configuration lives in `.env` (see `.env.example`). Architecture is described in
`README.md`.
