import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.scraping import http as scraping_http
from scripts.scraping.http import ScrapeSession
from scripts.scraping.site_discovery import discover_and_validate_site, validar_match


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scraping_http, "SCRAPING_CACHE_DIR", tmp_path / "scraping-cache")
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "unused")


def test_validar_match_finds_cnpj_in_footer():
    html = "<html><body><footer>CNPJ: 43.292.842/0001-77</footer></body></html>"
    result = validar_match(html, cnpj="43292842000177")
    assert result.matched is True
    assert "cnpj" in result.sinais


def test_validar_match_finds_razao_social():
    html = "<html><body><h1>Bem-vindo à Clinica Odontologica Quiles Ltda</h1></body></html>"
    result = validar_match(html, cnpj="00000000000000", razao_social="CLINICA ODONTOLOGICA QUILES LTDA")
    assert result.matched is True
    assert "razao_social" in result.sinais


def test_validar_match_finds_telefone():
    html = "<html><body>Ligue: (11) 3435-7093</body></html>"
    result = validar_match(html, cnpj="00000000000000", telefone="(11) 34357093")
    assert result.matched is True
    assert "telefone" in result.sinais


def test_validar_match_no_signal_is_weak_match():
    html = "<html><body>Site institucional genérico sem nenhum dado da empresa.</body></html>"
    result = validar_match(
        html, cnpj="43292842000177", razao_social="OUTRA EMPRESA LTDA", nome_fantasia="Outra", telefone="1199999999"
    )
    assert result.matched is False
    assert result.sinais == []


@pytest.mark.asyncio
async def test_discover_and_validate_site_confirms_match():
    session = ScrapeSession()
    with respx.mock() as mock:
        mock.get("https://empresa.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://empresa.com.br/").respond(
            200, text="<footer>CNPJ 43.292.842/0001-77</footer>"
        )
        result = await discover_and_validate_site(
            "https://empresa.com.br/", session, cnpj="43292842000177", min_delay=0.01, max_delay=0.02
        )

    assert result.matched is True
    assert "cnpj" in result.sinais
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_discover_and_validate_site_returns_no_match_without_raising():
    session = ScrapeSession()
    with respx.mock() as mock:
        mock.get("https://outrosite.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://outrosite.com.br/").respond(200, text="<html>nada a ver</html>")
        result = await discover_and_validate_site(
            "https://outrosite.com.br/", session, cnpj="43292842000177", min_delay=0.01, max_delay=0.02
        )

    assert result.matched is False


@pytest.mark.asyncio
async def test_discover_and_validate_site_handles_fetch_error_gracefully():
    session = ScrapeSession()
    with respx.mock() as mock:
        mock.get("https://bloqueado.com.br/robots.txt").respond(200, text="User-agent: *\nDisallow: /\n")
        result = await discover_and_validate_site(
            "https://bloqueado.com.br/", session, cnpj="43292842000177", min_delay=0.01, max_delay=0.02
        )

    assert result.matched is False
    assert result.erro is not None
    assert "RobotsDisallowed" in result.erro
