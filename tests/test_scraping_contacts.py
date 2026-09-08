import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.scraping import http as scraping_http
from scripts.scraping.contacts import discover_contacts, extract_contacts_from_html
from scripts.scraping.http import ScrapeSession


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scraping_http, "SCRAPING_CACHE_DIR", tmp_path / "scraping-cache")
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "unused")


FOOTER_HTML = """
<html><body>
<footer>
<p>Email: contato@empresa.com.br</p>
<p>Tel: (11) 3435-7093</p>
<a href="https://wa.me/5511999998888">Fale no WhatsApp</a>
<a href="https://instagram.com/empresa">@empresa</a>
<a href="https://www.facebook.com/empresa">Facebook</a>
</footer>
</body></html>
"""


def test_extract_contacts_from_html_finds_all_signals():
    result = extract_contacts_from_html(FOOTER_HTML)
    assert "contato@empresa.com.br" in result.emails
    assert "1134357093" in result.telefones
    assert "5511999998888" in result.whatsapp
    assert result.redes_sociais["instagram"] == "https://instagram.com/empresa"
    assert result.redes_sociais["facebook"] == "https://www.facebook.com/empresa"


def test_extract_contacts_from_html_empty_page_returns_empty_sets():
    result = extract_contacts_from_html("<html><body>Nada aqui.</body></html>")
    assert result.emails == set()
    assert result.telefones == set()
    assert result.whatsapp == set()
    assert result.redes_sociais == {}


@pytest.mark.asyncio
async def test_discover_contacts_crawls_home_and_high_signal_pages():
    session = ScrapeSession()
    home_html = """
    <html><body>
    <nav>
      <a href="/contato">Contato</a>
      <a href="/sobre">Sobre</a>
      <a href="https://outraempresa.com/contato">Site externo</a>
    </nav>
    {footer}
    </body></html>
    """.format(footer=FOOTER_HTML)
    contato_html = "<html><body><p>Fale conosco: vendas@empresa.com.br</p></body></html>"
    sobre_html = "<html><body><p>Sobre a empresa.</p></body></html>"

    with respx.mock() as mock:
        mock.get("https://empresa.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://empresa.com.br/").respond(200, text=home_html)
        mock.get("https://empresa.com.br/contato").respond(200, text=contato_html)
        mock.get("https://empresa.com.br/sobre").respond(200, text=sobre_html)

        result = await discover_contacts(
            "https://empresa.com.br/", session, max_pages=5, min_delay=0.01, max_delay=0.02
        )

    assert "contato@empresa.com.br" in result.emails
    assert "vendas@empresa.com.br" in result.emails
    assert len(result.paginas_visitadas) == 3
    assert "https://outraempresa.com/contato" not in result.paginas_visitadas


@pytest.mark.asyncio
async def test_discover_contacts_respects_max_pages_cap():
    session = ScrapeSession()
    home_html = """
    <html><body>
    <a href="/contato">Contato</a>
    <a href="/sobre">Sobre</a>
    <a href="/equipe">Equipe</a>
    <a href="/quem-somos">Quem somos</a>
    </body></html>
    """

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://empresa.com.br/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        mock.get("https://empresa.com.br/").respond(200, text=home_html)
        mock.get("https://empresa.com.br/contato").respond(200, text="<html></html>")
        mock.get("https://empresa.com.br/sobre").respond(200, text="<html></html>")
        mock.get("https://empresa.com.br/equipe").respond(200, text="<html></html>")
        mock.get("https://empresa.com.br/quem-somos").respond(200, text="<html></html>")

        result = await discover_contacts(
            "https://empresa.com.br/", session, max_pages=2, min_delay=0.01, max_delay=0.02
        )

    assert len(result.paginas_visitadas) == 2
