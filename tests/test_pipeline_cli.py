import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from scripts import pipeline_cli
from scripts.basecnpj import cache as cache_module
from scripts.pipeline import db as db_module

BASE_URL = "https://basecnpj.app/api/v1/"
runner = CliRunner()


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "DEFAULT_CACHE_DIR", tmp_path / "http-cache")
    monkeypatch.setenv("BASECNPJ_TOKEN", "fake")
    monkeypatch.setenv("BASECNPJ_BASE_URL", BASE_URL)


def _ok(data):
    return httpx.Response(200, json={"ok": True, "data": data})


def _invocar(tmp_path):
    db_path = tmp_path / "pipeline.sqlite3"
    result = runner.invoke(
        pipeline_cli.app,
        ["descobrir", "dentista", "--uf", "SP", "--db-path", str(db_path)],
    )
    return result, db_path


def test_cnpj_404_marca_nao_resolvido_e_segue(tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "avancada"}).mock(
            return_value=_ok({"total_pages": 1, "items": [{"cnpj_completo": "11111111000111"}]})
        )
        mock.get("", params={"route": "cnpj"}).mock(
            return_value=httpx.Response(404, json={"ok": False, "error": {"code": "not_found", "message": "x"}})
        )
        result, db_path = _invocar(tmp_path)

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert saida["total"] == 0
    assert saida["descartados"] == [{"cnpj": "11111111000111", "motivo": "cnpj nao encontrado no BaseCNPJ (404)"}]
    conn = db_module.connect(db_path)
    run_id = conn.execute("SELECT run_id FROM runs").fetchone()[0]
    leads = db_module.list_leads(conn, run_id, status="nao_resolvido")
    assert [lead["cnpj"] for lead in leads] == ["11111111000111"]


def test_avancada_403_sai_com_token_invalido(tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "avancada"}).mock(
            return_value=httpx.Response(403, json={"ok": False, "error": {"code": "forbidden", "message": "x"}})
        )
        result, _ = _invocar(tmp_path)

    assert result.exit_code == 1
    assert json.loads(result.stdout)["erro"] == "token_invalido"
    assert "Traceback" not in result.output


def test_status_diferente_de_ok_sai_com_preflight_falhou(tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "degraded"}))
        result, _ = _invocar(tmp_path)

    assert result.exit_code == 1
    saida = json.loads(result.stdout)
    assert saida["erro"] == "preflight_falhou"
    assert "degraded" in saida["mensagem"]


def test_descartado_na_validacao_aparece_em_descartados(tmp_path):
    detalhe = {
        "cnpj_basico": "11111111",
        "cnpj_completo_formatado": "11.111.111/0001-11",
        "razao_social": "EMPRESA INAPTA LTDA",
        "estabelecimento_matriz": {"situacao_cadastral": "04"},
        "cnaes": [{"tipo": "Principal", "cnae": "8630504", "desc": "Odontologia"}],
    }
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "avancada"}).mock(
            return_value=_ok({"total_pages": 1, "items": [{"cnpj_completo": "11111111000111"}]})
        )
        mock.get("", params={"route": "cnpj"}).mock(return_value=_ok(detalhe))
        result, _ = _invocar(tmp_path)

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert saida["total"] == 0
    assert saida["descartados"][0]["cnpj"] == "11111111000111"
    assert "situacao_cadastral=04" in saida["descartados"][0]["motivo"]
