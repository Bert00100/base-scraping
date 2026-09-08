import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.basecnpj import routes
from scripts.basecnpj.config import Settings

BASE_URL = "https://basecnpj.app/api/v1/"


@pytest.fixture
def settings():
    return Settings(token="fake-token", base_url=BASE_URL, default_timeout=10.0, heavy_route_timeout=60.0)


@pytest.mark.asyncio
async def test_status_hits_status_route_without_params(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).respond(200, json={"ok": True, "data": {"status": "ok"}})
        data = await routes.status(settings=settings)
    assert data == {"status": "ok"}


@pytest.mark.asyncio
async def test_busca_sends_q_page_per_page(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "busca", "q": "dentista", "page": "2", "per_page": "10"}).respond(
            200, json={"ok": True, "data": {"items": []}}
        )
        data = await routes.busca("dentista", page=2, per_page=10, settings=settings, use_cache=False)
    assert data == {"items": []}


@pytest.mark.asyncio
async def test_cnpj_strips_non_digits(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "cnpj", "cnpj": "00000000000191"}).respond(
            200, json={"ok": True, "data": {"razao_social": "BANCO DO BRASIL SA"}}
        )
        data = await routes.cnpj("00.000.000/0001-91", settings=settings, use_cache=False)
    assert data == {"razao_social": "BANCO DO BRASIL SA"}


@pytest.mark.asyncio
async def test_sugestao_sends_q(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "sugestao", "q": "dent"}).respond(
            200, json={"ok": True, "data": {"sugestoes": []}}
        )
        data = await routes.sugestao("dent", settings=settings, use_cache=False)
    assert data == {"sugestoes": []}


@pytest.mark.asyncio
async def test_avancada_omits_none_filters_and_sends_confirmed_param_names(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(
            "",
            params={
                "route": "avancada",
                "uf": "SP",
                "cnae": "8630504",
                "situacao": "02",
                "page": "1",
                "per_page": "15",
            },
        ).respond(200, json={"ok": True, "data": {"total": 0, "items": []}})
        data = await routes.avancada(uf="SP", cnae="8630504", situacao="02", settings=settings, use_cache=False)
    assert data == {"total": 0, "items": []}
    sent_query = dict(route.calls.last.request.url.params)
    assert "porte" not in sent_query
    assert "capital_min" not in sent_query


@pytest.mark.asyncio
async def test_rede_sends_cnpj_and_depth(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "rede", "cnpj": "00000000000191", "depth": "2"}).respond(
            200, json={"ok": True, "data": {"nodes": []}}
        )
        data = await routes.rede("00.000.000/0001-91", settings=settings, use_cache=False)
    assert data == {"nodes": []}


@pytest.mark.asyncio
async def test_avancada_uses_disk_cache_on_repeated_call(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "cache")
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "avancada", "uf": "SP", "page": "1", "per_page": "15"}).respond(
            200, json={"ok": True, "data": {"total": 1}}
        )
        first = await routes.avancada(uf="SP", settings=settings)
        second = await routes.avancada(uf="SP", settings=settings)
    assert first == second == {"total": 1}
    assert route.call_count == 1
