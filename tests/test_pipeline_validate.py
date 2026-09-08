from datetime import date

import pytest

from scripts.pipeline.icp import ICP
from scripts.pipeline.validate import validate_lead


def _raw(**overrides):
    base = {
        "cnpj_basico": "43292842",
        "cnpj_completo_formatado": "43.292.842/0001-77",
        "razao_social": "EMPRESA TESTE LTDA",
        "porte_codigo": "01",
        "estabelecimento_matriz": {
            "situacao_cadastral": "02",
            "situacao_descricao": "Ativa",
            "data_inicio_atividade": "2020-01-01",
            "cnae_principal_codigo": "8630504",
            "email": "contato@empresa.com",
        },
        "estabelecimentos": [{"cnpj_completo_formatado": "43.292.842/0001-77", "matriz_filial_codigo": "1"}],
        "cnaes": [{"tipo": "Principal", "cnae": "8630504", "desc": "Atividade odontológica"}],
        "telefones": [],
    }
    base.update(overrides)
    return base


def _icp(**overrides):
    defaults = dict(nicho="dentista", cnaes=["8630504"], porte="01", situacao="02")
    defaults.update(overrides)
    return ICP(**defaults)


@pytest.mark.asyncio
async def test_validado_happy_path_flags_contato_cadastral():
    result = await validate_lead("43292842000177", _icp(), raw=_raw(), hoje=date(2026, 1, 1))
    assert result.status == "validado"
    assert result.cnae_match == "principal"
    assert "contato_cadastral_disponivel" in result.flags
    assert "empresa_nova" not in result.flags


@pytest.mark.asyncio
async def test_descarta_quando_situacao_diferente_de_ativa():
    raw = _raw(estabelecimento_matriz={"situacao_cadastral": "08", "data_inicio_atividade": "2020-01-01"})
    result = await validate_lead("43292842000177", _icp(), raw=raw)
    assert result.status == "descartado"
    assert "situacao_cadastral" in result.discard_reason


@pytest.mark.asyncio
async def test_descarta_quando_cnae_fora_do_icp():
    raw = _raw(cnaes=[{"tipo": "Principal", "cnae": "4520001", "desc": "Oficina"}])
    result = await validate_lead("43292842000177", _icp(), raw=raw)
    assert result.status == "descartado"
    assert "cnae" in result.discard_reason


@pytest.mark.asyncio
async def test_mantem_com_flag_quando_cnae_so_secundario():
    raw = _raw(
        cnaes=[
            {"tipo": "Principal", "cnae": "4520001", "desc": "Oficina"},
            {"tipo": "Secundária", "cnae": "8630504", "desc": "Odontologia"},
        ]
    )
    result = await validate_lead("43292842000177", _icp(), raw=raw, hoje=date(2026, 1, 1))
    assert result.status == "validado"
    assert result.cnae_match == "secundario"
    assert "cnae_secundario" in result.flags


@pytest.mark.asyncio
async def test_descarta_quando_porte_fora_da_faixa():
    raw = _raw(porte_codigo="05")
    result = await validate_lead("43292842000177", _icp(porte="01"), raw=raw)
    assert result.status == "descartado"
    assert "porte" in result.discard_reason


@pytest.mark.asyncio
async def test_descarta_filial_quando_icp_pede_matriz():
    raw = _raw(
        estabelecimentos=[{"cnpj_completo_formatado": "43.292.842/0001-77", "matriz_filial_codigo": "2"}]
    )
    icp = _icp()
    icp.filtros_extra["matriz_filial"] = "1"
    result = await validate_lead("43292842000177", icp, raw=raw)
    assert result.status == "descartado"
    assert "filial" in result.discard_reason


@pytest.mark.asyncio
async def test_flag_empresa_nova_quando_abertura_recente():
    raw = _raw(estabelecimento_matriz={"situacao_cadastral": "02", "data_inicio_atividade": "2025-12-01", "cnae_principal_codigo": "8630504"})
    result = await validate_lead("43292842000177", _icp(), raw=raw, hoje=date(2026, 1, 1))
    assert result.status == "validado"
    assert "empresa_nova" in result.flags


@pytest.mark.asyncio
async def test_sem_contato_cadastral_nao_seta_flag():
    raw = _raw(estabelecimento_matriz={"situacao_cadastral": "02", "data_inicio_atividade": "2020-01-01", "cnae_principal_codigo": "8630504", "email": None})
    result = await validate_lead("43292842000177", _icp(), raw=raw, hoje=date(2026, 1, 1))
    assert result.status == "validado"
    assert "contato_cadastral_disponivel" not in result.flags
