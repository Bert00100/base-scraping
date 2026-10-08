import pytest
import respx

from scripts.basecnpj import cache as cache_module
from scripts.basecnpj.config import Settings
from scripts.pipeline.resolve import Candidato, resolve_candidato

BASE_URL = "https://basecnpj.app/api/v1/"


@pytest.fixture(autouse=True)
def isolated_http_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "http-cache")


@pytest.fixture
def settings():
    return Settings(token="fake", base_url=BASE_URL, default_timeout=10.0, heavy_route_timeout=60.0)


@pytest.mark.asyncio
async def test_resolve_via_sugestao_single_result(settings):
    candidato = Candidato(nome="Dentista & Paciente")
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "sugestao", "q": "Dentista & Paciente"}).respond(
            200,
            json={
                "ok": True,
                "data": {"items": [{"cnpj_formatado": "01.893.151/0001-89", "razao_social": "DENTISTA & PACIENTE"}]},
            },
        )
        result = await resolve_candidato(candidato, settings=settings)

    assert result.status == "resolvido"
    assert result.cnpj == "01893151000189"
    assert result.fonte == "sugestao"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_busca_when_sugestao_ambiguous(settings):
    candidato = Candidato(nome="Dentista", uf="SP")
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "sugestao", "q": "Dentista"}).respond(
            200,
            json={
                "ok": True,
                "data": {
                    "items": [
                        {"cnpj_formatado": "111"},
                        {"cnpj_formatado": "222"},
                    ]
                },
            },
        )
        mock.get("", params={"route": "busca", "q": "Dentista"}).respond(
            200,
            json={
                "ok": True,
                "data": {
                    "items": [
                        {"cnpj_formatado": "333", "uf": "SP"},
                        {"cnpj_formatado": "444", "uf": "RJ"},
                    ]
                },
            },
        )
        result = await resolve_candidato(candidato, settings=settings)

    assert result.status == "resolvido"
    assert result.cnpj == "333"
    assert result.fonte == "busca"


@pytest.mark.asyncio
async def test_resolve_marks_nao_resolvido_when_ambiguous_everywhere(settings):
    candidato = Candidato(nome="Dentista")  # sem UF/município para desempatar
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "sugestao", "q": "Dentista"}).respond(
            200,
            json={"ok": True, "data": {"items": [{"cnpj_formatado": "111"}, {"cnpj_formatado": "222"}]}},
        )
        mock.get("", params={"route": "busca", "q": "Dentista"}).respond(
            200,
            json={"ok": True, "data": {"items": [{"cnpj_formatado": "333"}, {"cnpj_formatado": "444"}]}},
        )
        result = await resolve_candidato(candidato, settings=settings)

    assert result.status == "nao_resolvido"
    assert result.cnpj is None


@pytest.mark.asyncio
async def test_resolve_marks_nao_resolvido_when_no_results(settings):
    candidato = Candidato(nome="Empresa Inexistente XYZ")
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "sugestao", "q": "Empresa Inexistente XYZ"}).respond(
            200, json={"ok": True, "data": {"items": []}}
        )
        mock.get("", params={"route": "busca", "q": "Empresa Inexistente XYZ"}).respond(
            200, json={"ok": True, "data": {"items": []}}
        )
        result = await resolve_candidato(candidato, settings=settings)

    assert result.status == "nao_resolvido"
