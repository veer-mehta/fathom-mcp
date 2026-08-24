from docs_mcp.mcp_client import maybe_json, parse_search_markdown, parse_sources_lines


def test_parse_search_markdown_vector_hits():
    text = (
        "### [Installation](https://docs.x.dev/install) (relevance 0.71)\n"
        "\n"
        "Install the package with pip.\n"
        "\n"
        "---\n"
        "\n"
        "### [Why use X — Guide > Setup](https://docs.x.dev/why) (relevance 0.55)\n"
        "\n"
        "Because it is fast.\n"
    )
    hits = parse_search_markdown(text)
    assert len(hits) == 2
    assert hits[0]["url"] == "https://docs.x.dev/install"
    assert hits[0]["title"] == "Installation"
    assert hits[0]["heading_path"] == []
    assert hits[0]["similarity"] == 0.71
    assert hits[0]["bm25_score"] is None
    assert hits[1]["heading_path"] == ["Guide", "Setup"]
    assert hits[1]["content"] == "Because it is fast."


def test_parse_search_markdown_keyword_and_noise():
    text = (
        "No matching documentation found. Call add_documentation first."
        "\n\n---\n\n"
        "### [Rust internals](https://docs.x.dev/rust) (match 0.1785)\n"
        "\n"
        "pydantic-core is written in Rust.\n"
    )
    hits = parse_search_markdown(text)
    assert len(hits) == 1
    assert hits[0]["similarity"] is None
    assert hits[0]["bm25_score"] == 0.1785
    assert parse_search_markdown("no results at all") == []


def test_parse_sources_lines():
    text = (
        "- pydantic@2.13: 6 pages, 34 chunks (updated 2026-08-22T12:00:00+00:00)\n"
        "- fastapi@0.115: 12 pages, 90 chunks\n"
        "some unrelated line\n"
    )
    sources = parse_sources_lines(text)
    assert [s["source_id"] for s in sources] == ["pydantic@2.13", "fastapi@0.115"]
    assert sources[0] == {
        "source_id": "pydantic@2.13",
        "pages": 6,
        "chunks": 34,
        "updated_at": "2026-08-22T12:00:00+00:00",
    }
    assert sources[1]["updated_at"] is None


def test_maybe_json_passthrough_and_error_text():
    assert maybe_json('{"job_id":"abc"}') == {"job_id": "abc"}
    assert maybe_json("Unknown job id: zz") == {"error": "Unknown job id: zz"}
