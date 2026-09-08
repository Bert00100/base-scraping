from __future__ import annotations

import asyncio
import random
import time
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from scripts.basecnpj.cache import get_or_fetch

USER_AGENT = "base-scraping/0.1 (+https://github.com/Mettric/base-scraping; contato B2B automatizado)"
SCRAPING_CACHE_DIR = Path(".cache/scraping")
CONTENT_TTL_SECONDS = 7 * 24 * 3600  # 7 dias (seção 9 do ARCTETURE.md)
MAX_PAGES_PER_DOMAIN = 5
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 5.0


class PageBudgetExceeded(Exception):
    """Teto de 5 páginas por domínio atingido (seção 9 do ARCTETURE.md)."""


class RobotsDisallowed(Exception):
    """robots.txt do domínio não permite acessar a URL."""


def domain_of(url: str) -> str:
    return urlparse(url).netloc


@dataclass
class ScrapeSession:
    """Estado de rate limiting de uma execução de scraping — sem estado global de
    módulo, pra não vazar entre execuções (nem entre testes).
    """

    page_counts: dict[str, int] = field(default_factory=dict)
    domain_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    domain_last_request: dict[str, float] = field(default_factory=dict)
    robots_cache: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)

    def lock_for(self, domain: str) -> asyncio.Lock:
        if domain not in self.domain_locks:
            self.domain_locks[domain] = asyncio.Lock()
        return self.domain_locks[domain]

    def pages_fetched(self, domain: str) -> int:
        return self.page_counts.get(domain, 0)


async def _get_robots(
    domain: str, session: ScrapeSession, *, client: httpx.AsyncClient
) -> urllib.robotparser.RobotFileParser:
    if domain in session.robots_cache:
        return session.robots_cache[domain]
    rp = urllib.robotparser.RobotFileParser()
    try:
        response = await client.get(
            f"https://{domain}/robots.txt", timeout=10.0, headers={"User-Agent": USER_AGENT}
        )
        if response.status_code < 400:
            rp.parse(response.text.splitlines())
        else:
            rp.parse([])  # sem robots.txt (404 etc.) — assume permitido
    except httpx.HTTPError:
        rp.parse([])
    session.robots_cache[domain] = rp
    return rp


async def _respect_domain_delay(
    domain: str, session: ScrapeSession, min_delay: float, max_delay: float
) -> None:
    last = session.domain_last_request.get(domain)
    if last is not None:
        elapsed = time.monotonic() - last
        alvo = random.uniform(min_delay, max_delay)
        espera = alvo - elapsed
        if espera > 0:
            await asyncio.sleep(espera)
    session.domain_last_request[domain] = time.monotonic()


async def fetch(
    url: str,
    session: ScrapeSession,
    *,
    max_pages_per_domain: int = MAX_PAGES_PER_DOMAIN,
    min_delay: float = MIN_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    cache_dir: Path | None = None,
    ttl: float = CONTENT_TTL_SECONDS,
    use_cache: bool = True,
    client: httpx.AsyncClient | None = None,
    respect_robots: bool = True,
) -> dict[str, Any]:
    """Busca uma URL respeitando: 1 requisição simultânea por domínio (lock),
    delay de 2-5s com jitter entre requisições ao mesmo domínio, teto de páginas
    por domínio, robots.txt/Crawl-delay, e cache em disco de 7 dias.
    """
    domain = domain_of(url)
    if session.pages_fetched(domain) >= max_pages_per_domain:
        raise PageBudgetExceeded(f"teto de {max_pages_per_domain} páginas por domínio atingido: {domain}")

    owns_client = client is None
    http_client = client or httpx.AsyncClient(headers={"User-Agent": USER_AGENT})

    try:
        effective_min, effective_max = min_delay, max_delay
        if respect_robots:
            rp = await _get_robots(domain, session, client=http_client)
            if not rp.can_fetch(USER_AGENT, url):
                raise RobotsDisallowed(f"robots.txt não permite: {url}")
            crawl_delay = rp.crawl_delay(USER_AGENT)
            if crawl_delay:
                effective_min = max(effective_min, float(crawl_delay))
                effective_max = max(effective_max, effective_min)

        async def _do_fetch() -> dict[str, Any]:
            async with session.lock_for(domain):
                await _respect_domain_delay(domain, session, effective_min, effective_max)
                response = await http_client.get(url, timeout=15.0, headers={"User-Agent": USER_AGENT})
                return {"status_code": response.status_code, "text": response.text, "url": str(response.url)}

        if use_cache:
            resultado = await get_or_fetch(
                "page",
                {"url": url},
                _do_fetch,
                cache_dir=cache_dir if cache_dir is not None else SCRAPING_CACHE_DIR,
                ttl=ttl,
            )
        else:
            resultado = await _do_fetch()

        session.page_counts[domain] = session.pages_fetched(domain) + 1
        return resultado
    finally:
        if owns_client:
            await http_client.aclose()
