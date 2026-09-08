import asyncio
import time

import httpx
import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.scraping import http as scraping_http
from scripts.scraping.http import PageBudgetExceeded, RobotsDisallowed, ScrapeSession, fetch


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scraping_http, "SCRAPING_CACHE_DIR", tmp_path / "scraping-cache")
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "unused")


def _allow_all_robots(mock):
    mock.get("https://example.com/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")


@pytest.mark.asyncio
async def test_fetch_raises_when_page_budget_exceeded():
    session = ScrapeSession(page_counts={"example.com": 5})
    with pytest.raises(PageBudgetExceeded):
        await fetch("https://example.com/contato", session, max_pages_per_domain=5)


@pytest.mark.asyncio
async def test_fetch_respects_robots_disallow():
    session = ScrapeSession()
    with respx.mock() as mock:
        mock.get("https://example.com/robots.txt").respond(200, text="User-agent: *\nDisallow: /\n")
        with pytest.raises(RobotsDisallowed):
            await fetch("https://example.com/contato", session, min_delay=0.01, max_delay=0.02)


@pytest.mark.asyncio
async def test_fetch_returns_page_content_and_increments_page_count():
    session = ScrapeSession()
    with respx.mock() as mock:
        _allow_all_robots(mock)
        mock.get("https://example.com/contato").respond(200, text="<html>contato</html>")
        result = await fetch("https://example.com/contato", session, min_delay=0.01, max_delay=0.02)

    assert result["status_code"] == 200
    assert "contato" in result["text"]
    assert session.pages_fetched("example.com") == 1


@pytest.mark.asyncio
async def test_fetch_uses_disk_cache_on_repeated_url():
    session = ScrapeSession()
    with respx.mock() as mock:
        _allow_all_robots(mock)
        route = mock.get("https://example.com/contato").respond(200, text="<html>contato</html>")
        await fetch("https://example.com/contato", session, min_delay=0.01, max_delay=0.02)
        await fetch("https://example.com/contato", session, min_delay=0.01, max_delay=0.02)

    assert route.call_count == 1


@pytest.mark.asyncio
async def test_fetch_enforces_minimum_delay_between_same_domain_requests():
    session = ScrapeSession()
    with respx.mock() as mock:
        _allow_all_robots(mock)
        mock.get("https://example.com/a").respond(200, text="a")
        mock.get("https://example.com/b").respond(200, text="b")

        t0 = time.monotonic()
        await fetch("https://example.com/a", session, min_delay=0.05, max_delay=0.05, use_cache=False)
        await fetch("https://example.com/b", session, min_delay=0.05, max_delay=0.05, use_cache=False)
        elapsed = time.monotonic() - t0

    assert elapsed >= 0.05


@pytest.mark.asyncio
async def test_fetch_serializes_concurrent_requests_to_same_domain():
    session = ScrapeSession()
    in_flight = 0
    max_in_flight = 0

    async def slow_responder(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return httpx.Response(200, text="ok")

    with respx.mock() as mock:
        _allow_all_robots(mock)
        mock.get("https://example.com/a").mock(side_effect=slow_responder)
        mock.get("https://example.com/b").mock(side_effect=slow_responder)

        await asyncio.gather(
            fetch("https://example.com/a", session, min_delay=0.0, max_delay=0.0, use_cache=False),
            fetch("https://example.com/b", session, min_delay=0.0, max_delay=0.0, use_cache=False),
        )

    assert max_in_flight == 1


@pytest.mark.asyncio
async def test_different_domains_do_not_share_page_budget():
    session = ScrapeSession(page_counts={"a.example.com": 5})
    with respx.mock() as mock:
        mock.get("https://b.example.com/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://b.example.com/contato").respond(200, text="ok")
        result = await fetch("https://b.example.com/contato", session, min_delay=0.01, max_delay=0.02)

    assert result["status_code"] == 200
