import asyncio
import json
import logging
import os
import re
import sys

from docs_mcp.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


class McpBridge:
    """Runs the docs-mcp MCP server as a stdio subprocess and proxies tool calls.

    The MCP SDK's stdio transport must be entered/exited inside one task, so a
    dedicated worker task owns the session; callers talk to it via a queue.
    """

    def __init__(self, command: list[str] | None = None, default_timeout: float = 60.0):
        self._command = command or [sys.executable, "-m", "docs_mcp.server"]
        self._default_timeout = default_timeout
        self._queue: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def call(self, tool: str, arguments: dict, timeout: float | None = None) -> str:
        await self._ensure_running()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        assert self._queue is not None
        await self._queue.put((tool, arguments, fut))
        try:
            return await asyncio.wait_for(fut, timeout or self._default_timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"MCP tool '{tool}' timed out after {timeout or self._default_timeout}s"
            ) from None

    async def close(self) -> None:
        if self._worker is not None and not self._worker.done():
            if self._queue is not None:
                await self._queue.put(None)
            try:
                # wait_for cancels the worker on timeout, which unwinds the
                # stdio context managers and terminates the subprocess.
                await asyncio.wait_for(self._worker, timeout=5)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                pass
        self._worker = None
        self._queue = None

    async def _ensure_running(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        async with self._lock:
            if self._worker is not None and not self._worker.done():
                return
            logger.info("starting MCP server subprocess: %s", " ".join(self._command))
            self._queue = asyncio.Queue()
            self._worker = asyncio.create_task(self._run_session())

    async def _run_session(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        queue = self._queue
        assert queue is not None
        params = StdioServerParameters(
            command=self._command[0],
            args=self._command[1:],
            env={**os.environ},
            cwd=str(PROJECT_ROOT),
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.info("MCP session ready")
                    while True:
                        item = await queue.get()
                        if item is None:
                            return
                        tool, args, fut = item
                        try:
                            result = await session.call_tool(tool, args)
                            text = (
                                result.content[0].text if result.content else ""
                            )
                            if not fut.done():
                                fut.set_result(text)
                        except Exception as exc:
                            if not fut.done():
                                fut.set_exception(exc)
                            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("MCP bridge worker died")
            while not queue.empty():
                _, _, pending_fut = queue.get_nowait()
                if not pending_fut.done():
                    pending_fut.set_exception(
                        RuntimeError(f"MCP server session failed: {exc}")
                    )


SEARCH_HEADER_RE = re.compile(
    r"^### \[(?P<header>[^\]]+)\]\((?P<url>[^)]+)\)\s+\((?P<score>[^)]+)\)$"
)
SOURCE_LINE_RE = re.compile(
    r"^-\s(?P<sid>.+?):\s(?P<pages>\d+) pages,\s(?P<chunks>\d+) chunks"
    r"(?:\s\(updated\s(?P<updated>[^)]+)\))?$"
)


def parse_search_markdown(text: str) -> list[dict]:
    hits: list[dict] = []
    for block in text.split("\n\n---\n\n"):
        block = block.strip()
        if not block.startswith("### "):
            continue
        first_line, _, content = block.partition("\n")
        match = SEARCH_HEADER_RE.match(first_line.strip())
        if not match:
            continue
        score_text = match.group("score").strip()
        similarity = bm25 = None
        kind, _, value = score_text.partition(" ")
        try:
            if kind == "relevance":
                similarity = float(value)
            elif kind == "match":
                bm25 = float(value)
        except ValueError:
            pass
        header = match.group("header")
        title, sep, crumb = header.partition(" — ")
        hits.append(
            {
                "url": match.group("url"),
                "title": title or None,
                "heading_path": crumb.split(" > ") if sep else [],
                "content": content.strip(),
                "similarity": similarity,
                "bm25_score": bm25,
            }
        )
    return hits


def parse_sources_lines(text: str) -> list[dict]:
    sources = []
    for line in text.splitlines():
        match = SOURCE_LINE_RE.match(line.strip())
        if not match:
            continue
        sources.append(
            {
                "source_id": match.group("sid"),
                "pages": int(match.group("pages")),
                "chunks": int(match.group("chunks")),
                "updated_at": match.group("updated"),
            }
        )
    return sources


def maybe_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    return {"error": stripped}
