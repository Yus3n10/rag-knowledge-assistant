from pathlib import Path
from scripts.osha.fetch import fetch_html


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append(url)
        return FakeResponse(self.text)


def test_fetches_and_writes_cache(tmp_path):
    cache = tmp_path / "1910.147.html"
    session = FakeSession("<html>live</html>")

    result = fetch_html("https://example.gov/x", cache, session=session, delay=0)

    assert result == "<html>live</html>"
    assert cache.read_text(encoding="utf-8") == "<html>live</html>"
    assert session.calls == ["https://example.gov/x"]


def test_reads_cache_without_network(tmp_path):
    cache = tmp_path / "1910.147.html"
    cache.write_text("<html>cached</html>", encoding="utf-8")
    session = FakeSession("<html>live</html>")

    result = fetch_html("https://example.gov/x", cache, session=session, delay=0)

    assert result == "<html>cached</html>"
    assert session.calls == []
