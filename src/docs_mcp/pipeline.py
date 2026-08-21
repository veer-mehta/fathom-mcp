import asyncio
import json
import logging
import sys
import tempfile
from dataclasses import asdict, dataclass

from docs_mcp.config import settings
from docs_mcp.embeddings import get_embedding_provider
from docs_mcp.processing.chunker import chunk_markdown
from docs_mcp.processing.extract import html_to_markdown
from docs_mcp.storage.db import Database

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


@dataclass
class IngestResult:
    source_id: str
    pages_crawled: int
    pages_indexed: int
    chunks_indexed: int
    errors: int


async def ingest_documentation(
    db: Database,
    name: str,
    version: str,
    base_url: str,
    max_depth: int | None = None,
    max_pages: int | None = None,
) -> IngestResult:
    source_id = f"{name}@{version}"
    provider = get_embedding_provider()
    await db.ensure_schema(provider.dimensions)

    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "docs_mcp.scraper.runner",
            "--url",
            base_url,
            "--depth",
            str(max_depth if max_depth is not None else settings.crawl_max_depth),
            "--max-pages",
            str(max_pages if max_pages is not None else settings.crawl_max_pages),
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr_file,
            limit=64 * 1024 * 1024,
        )

        result = IngestResult(
            source_id=source_id,
            pages_crawled=0,
            pages_indexed=0,
            chunks_indexed=0,
            errors=0,
        )
        pending: list[dict] = []

        async def flush() -> None:
            nonlocal pending
            if not pending:
                return
            vectors = await provider.embed([row["content"] for row in pending])
            for row, vector in zip(pending, vectors):
                row["embedding"] = vector
            await db.upsert_chunks(pending)
            result.chunks_indexed += len(pending)
            pending = []

        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                page = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("skipping malformed crawler output line")
                result.errors += 1
                continue

            result.pages_crawled += 1
            markdown = html_to_markdown(page.get("html") or "", page.get("url") or "")
            if not markdown:
                result.errors += 1
                continue
            chunks = chunk_markdown(markdown)
            for index, chunk in enumerate(chunks):
                pending.append(
                    {
                        "source_id": source_id,
                        "url": page["url"],
                        "title": page.get("title"),
                        "content": chunk.content,
                        "heading_path": chunk.heading_path,
                        "chunk_index": index,
                        "provider": provider.name,
                        "metadata": {},
                    }
                )
            result.pages_indexed += 1
            if len(pending) >= EMBED_BATCH_SIZE:
                await flush()

        await flush()
        return_code = await proc.wait()
        if return_code != 0:
            result.errors += 1
            stderr_file.seek(0)
            tail = stderr_file.read().decode(errors="replace")[-2000:]
            logger.error("crawler exited with %s: %s", return_code, tail)

    return asdict(result)
