import time
from pathlib import Path

import requests

USER_AGENT = "rag-knowledge-assistant/0.1 (portfolio project; contact pgeagoni@gmail.com)"


def fetch_html(url, cache_path, *, session=None, delay=1.0):
    cache_path = Path(cache_path)
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    session = session or requests.Session()
    response = session.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    html = response.text

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    if delay:
        time.sleep(delay)
    return html
