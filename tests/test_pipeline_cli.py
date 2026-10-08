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


@pytest.mark.parametrize(
    ("status_code", "code"),
    [(401, "unauthorized"), (403, "forbidden")],
)
def test_avancada_sem_autorizacao_sai_com_token_invalido(tmp_path, status_code, code):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "avancada"}).mock(
            return_value=httpx.Response(status_code, json={"ok": False, "error": {"code": code, "message": "x"}})
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


def _detalhe(cnpj_basico="11111111", cnpj="11.111.111/0001-11", situacao="02"):
    return {
        "cnpj_basico": cnpj_basico,
        "cnpj_completo_formatado": cnpj,
        "razao_social": "EMPRESA TESTE LTDA",
        "estabelecimento_matriz": {"situacao_cadastral": situacao},
        "cnaes": [{"tipo": "Principal", "cnae": "8630504", "desc": "Odontologia"}],
    }


def _invocar_lista(tmp_path, itens, *extra):
    arquivo = tmp_path / "lista.json"
    arquivo.write_text(json.dumps(itens))
    return runner.invoke(pipeline_cli.app, ["validar-lista", "--arquivo", str(arquivo), *extra])


def _cnpj_por_param(detalhes):
    def responder(request):
        cnpj = request.url.params["cnpj"]
        if cnpj in detalhes:
            return _ok(detalhes[cnpj])
        return httpx.Response(404, json={"ok": False, "error": {"code": "not_found", "message": "x"}})

    return responder


def test_validar_lista_cnpj_direto(tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "cnpj"}).mock(side_effect=_cnpj_por_param({"11111111000111": _detalhe()}))
        result = _invocar_lista(tmp_path, [{"cnpj": "11.111.111/0001-11"}])

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert saida["total"] == 1
    assert saida["leads"][0]["cnpj"] == "11111111000111"
    assert saida["descartados"] == []
    assert saida["nao_resolvidos"] == []
    assert "aviso" not in saida


def test_validar_lista_nome_resolvido(tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "sugestao"}).mock(
            return_value=_ok({"items": [{"cnpj_formatado": "11.111.111/0001-11", "razao_social": "EMPRESA TESTE"}]})
        )
        mock.get("", params={"route": "cnpj"}).mock(side_effect=_cnpj_por_param({"11111111000111": _detalhe()}))
        result = _invocar_lista(tmp_path, [{"nome": "Empresa Teste"}])

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert [lead["cnpj"] for lead in saida["leads"]] == ["11111111000111"]
    assert saida["nao_resolvidos"] == []


def test_validar_lista_nome_ambiguo_vai_para_nao_resolvidos(tmp_path):
    ambiguo = _ok({"items": [{"cnpj_formatado": "11.111.111/0001-11"}, {"cnpj_formatado": "22.222.222/0001-22"}]})
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "sugestao"}).mock(return_value=ambiguo)
        mock.get("", params={"route": "busca"}).mock(return_value=ambiguo)
        result = _invocar_lista(tmp_path, [{"nome": "Clinica Comum"}])

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert saida["total"] == 0
    assert saida["nao_resolvidos"][0]["nome"] == "Clinica Comum"


def test_validar_lista_404_e_descartado_na_validacao(tmp_path):
    detalhes = {"22222222000122": _detalhe("22222222", "22.222.222/0001-22", situacao="04")}
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        mock.get("", params={"route": "cnpj"}).mock(side_effect=_cnpj_por_param(detalhes))
        result = _invocar_lista(tmp_path, [{"cnpj": "11111111000111"}, {"cnpj": "22222222000122"}])

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert saida["total"] == 0
    assert saida["descartados"][0] == {"cnpj": "11111111000111", "motivo": "cnpj nao encontrado no BaseCNPJ (404)"}
    assert "situacao_cadastral=04" in saida["descartados"][1]["motivo"]


def test_validar_lista_respeita_teto_de_100_itens(tmp_path):
    itens = [{"cnpj": f"{i:014d}"} for i in range(1, 106)]
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "ok"}))
        rota_cnpj = mock.get("", params={"route": "cnpj"}).mock(side_effect=_cnpj_por_param({}))
        result = _invocar_lista(tmp_path, itens)

    assert result.exit_code == 0
    saida = json.loads(result.stdout)
    assert rota_cnpj.call_count == 100
    assert len(saida["descartados"]) == 100
    assert "5 item(ns)" in saida["aviso"]


def test_validar_lista_preflight_falhou(tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).mock(return_value=_ok({"status": "degraded"}))
        result = _invocar_lista(tmp_path, [{"cnpj": "11111111000111"}])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["erro"] == "preflight_falhou"
