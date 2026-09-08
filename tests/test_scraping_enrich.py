import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.scraping import http as scraping_http
from scripts.scraping.enrich import enrich
from scripts.scraping.http import ScrapeSession

_MX_OK = lambda dominio: ["mx1.exemplo.com"]  # noqa: E731


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scraping_http, "SCRAPING_CACHE_DIR", tmp_path / "scraping-cache")
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "unused")


HOME_HTML = """
<html><body>
<nav><a href="/contato">Contato</a></nav>
<footer>
<p>CNPJ 43.292.842/0001-77</p>
<p>Email: contato@empresa.com.br</p>
<a href="https://instagram.com/empresa">Instagram</a>
</footer>
</body></html>
"""

CONTATO_HTML = "<html><body><p>Fale com a gente: vendas@empresa.com.br</p></body></html>"


@pytest.mark.asyncio
async def test_enrich_full_happy_path():
    session = ScrapeSession()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://empresa.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://empresa.com.br/").respond(200, text=HOME_HTML)
        mock.get("https://empresa.com.br/contato").respond(200, text=CONTATO_HTML)

        result = await enrich(
            "https://empresa.com.br/",
            session,
            cnpj="43292842000177",
            razao_social="EMPRESA TESTE LTDA",
            mx_resolver=_MX_OK,
            min_delay=0.01,
            max_delay=0.02,
        )

    assert result.site_matched is True
    assert result.requer_navegador is False
    assert {e.email for e in result.emails} == {"contato@empresa.com.br", "vendas@empresa.com.br"}
    assert result.redes_sociais["instagram"] == "https://instagram.com/empresa"
    assert result.erro is None


@pytest.mark.asyncio
async def test_enrich_returns_erro_when_no_candidate_url():
    session = ScrapeSession()
    result = await enrich(None, session, cnpj="43292842000177")
    assert result.erro == "sem_site_candidato"
    assert result.site_matched is False


@pytest.mark.asyncio
async def test_enrich_marks_weak_match_and_skips_enrichment():
    session = ScrapeSession()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://outrositequalquer.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://outrositequalquer.com.br/").respond(200, text="<html><body>nada a ver</body></html>")

        result = await enrich(
            "https://outrositequalquer.com.br/", session, cnpj="43292842000177", min_delay=0.01, max_delay=0.02
        )

    assert result.site_matched is False
    assert result.erro == "match_fraco"
    assert result.emails == []


@pytest.mark.asyncio
async def test_enrich_marks_requer_navegador_for_spa_shell():
    session = ScrapeSession()
    spa_html = '<html><body><div id="root">CNPJ 43.292.842/0001-77</div><script src="/app.js"></script></body></html>'
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://spa.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://spa.com.br/").respond(200, text=spa_html)

        result = await enrich("https://spa.com.br/", session, cnpj="43292842000177", min_delay=0.01, max_delay=0.02)

    assert result.site_matched is True
    assert result.requer_navegador is True
    assert result.emails == []


@pytest.mark.asyncio
async def test_enrich_survives_fetch_failure_without_raising():
    session = ScrapeSession()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://bloqueado.com.br/robots.txt").respond(200, text="User-agent: *\nDisallow: /\n")

        result = await enrich(
            "https://bloqueado.com.br/", session, cnpj="43292842000177", min_delay=0.01, max_delay=0.02
        )

    assert result.site_matched is False
    assert result.erro is not None
