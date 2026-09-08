import httpx
import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.basecnpj.config import Settings
from scripts.pipeline import db as db_module
from scripts.pipeline import discovery
from scripts.pipeline.icp import ICP

BASE_URL = "https://basecnpj.app/api/v1/"


@pytest.fixture(autouse=True)
def isolated_http_cache(tmp_path, monkeypatch):
    # sem isso, os testes leriam do cache real em disco deixado por smoke tests
    # manuais contra a API (mesmos params: cnae=8630504, uf=SP, situacao=02, per_page=2)
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "http-cache")


@pytest.fixture
def settings():
    return Settings(token="fake", base_url=BASE_URL, default_timeout=10.0, heavy_route_timeout=60.0)


@pytest.fixture
def conn(tmp_path):
    return db_module.connect(tmp_path / "pipeline.sqlite3")


def _page(items, total_pages):
    return httpx.Response(
        200, json={"ok": True, "data": {"total_pages": total_pages, "items": items}}
    )


def _item(cnpj: str) -> dict:
    return {"cnpj_completo": cnpj, "razao_social": f"EMPRESA {cnpj}"}


@pytest.mark.asyncio
async def test_discover_paginates_until_exhausted(settings, conn):
    icp = ICP(nicho="dentista", cnaes=["8630504"], uf="SP")
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "avancada", "cnae": "8630504", "uf": "SP", "situacao": "02"})
        route.side_effect = [
            _page([_item("111"), _item("222")], total_pages=2),
            _page([_item("333")], total_pages=2),
        ]
        leads = await discovery.discover(icp, conn=conn, run_id="run1", target_leads=100, per_page=2, settings=settings)

    assert {lead["cnpj"] for lead in leads} == {"111", "222", "333"}
    assert route.call_count == 2
    checkpoint = db_module.get_checkpoint(conn, "run1", "8630504")
    assert checkpoint == {"next_page": 3, "exhausted": True}


@pytest.mark.asyncio
async def test_discover_stops_exactly_at_target_leads(settings, conn):
    icp = ICP(nicho="dentista", cnaes=["8630504"], uf="SP")
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "avancada", "cnae": "8630504", "uf": "SP", "situacao": "02"})
        route.side_effect = [
            _page([_item("111"), _item("222")], total_pages=5),
            _page([_item("333"), _item("444")], total_pages=5),
        ]
        leads = await discovery.discover(icp, conn=conn, run_id="run1", target_leads=3, per_page=2, settings=settings)

    assert len(leads) == 3
    assert {lead["cnpj"] for lead in leads} == {"111", "222", "333"}
    # não deve ter marcado como exaurido — página 2 ficou parcialmente processada
    checkpoint = db_module.get_checkpoint(conn, "run1", "8630504")
    assert checkpoint == {"next_page": 2, "exhausted": False}


@pytest.mark.asyncio
async def test_discover_resumes_from_checkpoint(settings, conn):
    icp = ICP(nicho="dentista", cnaes=["8630504"], uf="SP")
    db_module.save_checkpoint(conn, "run1", "8630504", next_page=2)
    db_module.upsert_lead(conn, "run1", "111", status="descoberto", discovery=_item("111"))

    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "avancada", "cnae": "8630504", "uf": "SP", "situacao": "02"})
        route.side_effect = [_page([_item("222")], total_pages=2)]
        leads = await discovery.discover(icp, conn=conn, run_id="run1", target_leads=100, per_page=2, settings=settings)

    assert route.call_count == 1  # só buscou a página 2, não repetiu a 1
    assert {lead["cnpj"] for lead in leads} == {"111", "222"}


@pytest.mark.asyncio
async def test_discover_dedups_same_cnpj_across_cnaes(settings, conn):
    icp = ICP(nicho="oficina", cnaes=["4520001", "4520002"], uf="SP")
    with respx.mock(base_url=BASE_URL) as mock:
        route1 = mock.get("", params={"route": "avancada", "cnae": "4520001", "uf": "SP", "situacao": "02"})
        route1.side_effect = [_page([_item("111")], total_pages=1)]
        route2 = mock.get("", params={"route": "avancada", "cnae": "4520002", "uf": "SP", "situacao": "02"})
        route2.side_effect = [_page([_item("111"), _item("222")], total_pages=1)]

        leads = await discovery.discover(icp, conn=conn, run_id="run1", target_leads=100, per_page=15, settings=settings)

    assert {lead["cnpj"] for lead in leads} == {"111", "222"}


@pytest.mark.asyncio
async def test_discover_raises_when_icp_needs_confirmation(settings, conn):
    icp = ICP(nicho="fabrica de foguetes", cnaes=[], needs_confirmation=True)
    with pytest.raises(ValueError):
        await discovery.discover(icp, conn=conn, run_id="run1", settings=settings)
