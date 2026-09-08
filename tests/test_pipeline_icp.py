import pytest
import respx

from scripts.basecnpj.config import Settings
from scripts.pipeline import icp

CNAE_DICT_PATH = "references/cnae.md"


def test_load_cnae_dictionary_parses_all_real_entries():
    entries = icp.load_cnae_dictionary(CNAE_DICT_PATH)
    assert len(entries) == 11
    aliases = {a for e in entries for a in e.aliases}
    assert "dentista" in aliases
    assert "padaria" in aliases
    assert "ótica" in aliases


def test_load_cnae_dictionary_handles_backtick_prefix():
    entries = icp.load_cnae_dictionary(CNAE_DICT_PATH)
    dentista = next(e for e in entries if "dentista" in e.aliases)
    assert dentista.cnaes == ["8630504"]


def test_load_cnae_dictionary_derives_multi_cnae_from_raw_column():
    entries = icp.load_cnae_dictionary(CNAE_DICT_PATH)
    pet_shop = next(e for e in entries if "pet shop" in e.aliases)
    assert set(pet_shop.cnaes) == {"4789004", "9609208"}


def test_resolve_nicho_exact_alias_match():
    entries = icp.load_cnae_dictionary(CNAE_DICT_PATH)
    entry = icp.resolve_nicho("dentista", entries)
    assert entry is not None
    assert entry.cnaes == ["8630504"]


def test_resolve_nicho_partial_match():
    entries = icp.load_cnae_dictionary(CNAE_DICT_PATH)
    entry = icp.resolve_nicho("clínica odontológica de bairro", entries)
    assert entry is not None
    assert "clínica odontológica" in entry.aliases


def test_resolve_nicho_unknown_returns_none():
    entries = icp.load_cnae_dictionary(CNAE_DICT_PATH)
    assert icp.resolve_nicho("fabrica de foguetes", entries) is None


def test_build_icp_known_nicho_resolves_without_confirmation():
    result = icp.build_icp(nicho="dentista", uf="SP", porte="ME", cnae_dict_path=CNAE_DICT_PATH)
    assert result.needs_confirmation is False
    assert result.cnaes == ["8630504"]
    assert result.porte == "01"
    assert result.situacao == "02"


def test_build_icp_unknown_nicho_needs_confirmation():
    result = icp.build_icp(nicho="fabrica de foguetes", cnae_dict_path=CNAE_DICT_PATH)
    assert result.needs_confirmation is True
    assert result.cnaes == []


def test_icp_filtros_por_cnae_includes_all_set_fields():
    result = icp.build_icp(nicho="dentista", uf="SP", municipio="Campinas", porte="ME", cnae_dict_path=CNAE_DICT_PATH)
    filtros = result.filtros_por_cnae("8630504")
    assert filtros == {"cnae": "8630504", "uf": "SP", "municipio": "Campinas", "porte": "01", "situacao": "02"}


def test_build_icp_cep_filters_by_neighborhood_prefix():
    result = icp.build_icp(nicho="ótica", uf="SP", cep="0507", cnae_dict_path=CNAE_DICT_PATH)
    filtros = result.filtros_por_cnae("4774100")
    assert filtros["cep"] == "0507"


@pytest.mark.asyncio
async def test_preflight_calls_status_route():
    settings = Settings(token=None, base_url="https://basecnpj.app/api/v1/", default_timeout=10.0, heavy_route_timeout=60.0)
    with respx.mock(base_url=settings.base_url) as mock:
        mock.get("", params={"route": "status"}).respond(200, json={"ok": True, "data": {"status": "ok"}})
        data = await icp.preflight(settings=settings)
    assert data == {"status": "ok"}
