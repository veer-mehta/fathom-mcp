from docs_mcp.processing.extract import html_to_markdown

HTML = """
<html>
<head><title>Docs</title><script>var tracking = 1;</script></head>
<body>
<nav><a href="/home">Home</a></nav>
<article>
<h1>Hello</h1>
<p>World with a <a href="https://example.com/x">link</a>.</p>
<table><tr><th>A</th><td>1</td></tr></table>
</article>
<footer>copyright junk</footer>
</body>
</html>
"""


def test_extracts_main_content_as_markdown():
    markdown = html_to_markdown(HTML, "https://example.com/docs")
    assert markdown is not None
    assert "Hello" in markdown
    assert "World" in markdown


def test_output_is_markdown():
    markdown = html_to_markdown(HTML, "https://example.com/docs")
    assert markdown is not None
    assert "#" in markdown


def test_fallback_strips_scripts_and_junk():
    raw = "<html><body><script>alert(1)</script><nav>menu</nav><p>kept content</p></body></html>"
    markdown = html_to_markdown(raw, "https://example.com/page")
    assert markdown is not None
    assert "alert" not in markdown
    assert "kept content" in markdown


def test_empty_html_returns_none():
    assert html_to_markdown("", "https://example.com") is None
