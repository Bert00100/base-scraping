from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from scripts.pipeline import db as db_module
from scripts.pipeline import discovery
from scripts.pipeline import icp as icp_module
from scripts.pipeline.export import export_leads, build_lead_json
from scripts.pipeline.score import compute_score
from scripts.pipeline.validate import validate_lead
from scripts.scraping.enrich import enrich
from scripts.scraping.http import ScrapeSession

app = typer.Typer(help="Pipeline do base-scraping — S0→S3 (descobrir) e S0→S4→S6 (prospectar, sem S5).")

TARGET_LEADS = 100  # decisão fechada, seção 11 do ARCTETURE.md — sem override de CLI


def _run(coro):
    return asyncio.run(coro)


def _resolve_icp_or_exit(
    nicho: str, uf: str | None, municipio: str | None, porte: str | None, situacao: str, cep: str | None
) -> icp_module.ICP:
    icp = icp_module.build_icp(nicho=nicho, uf=uf, municipio=municipio, porte=porte, situacao=situacao, cep=cep)
    if icp.needs_confirmation:
        typer.echo(
            json.dumps(
                {
                    "erro": "nicho_nao_encontrado",
                    "mensagem": (
                        f"Nicho '{nicho}' não está em references/cnae.md. "
                        "Confirme o(s) CNAE(s) certo(s) com o usuário antes de rodar a descoberta."
                    ),
                },
                ensure_ascii=False,
            )
        )
        raise typer.Exit(code=1)
    return icp


async def _descobrir_ate_validar(
    icp: icp_module.ICP,
    *,
    nicho: str,
    uf: str | None,
    municipio: str | None,
    porte: str | None,
    situacao: str,
    cep: str | None,
    db_path: str | None,
) -> tuple[Any, str, list[dict[str, Any]]]:
    """S0→S3: roda preflight, descoberta (com checkpoint) e validação dos leads
    ainda não processados. Devolve (conn, run_id, leads_validados_desta_execucao_em_diante).
    """
    status = await icp_module.preflight()
    if status.get("status") != "ok":
        raise RuntimeError(f"preflight falhou: {status}")

    conn = db_module.connect(Path(db_path) if db_path else None)
    params = {"nicho": nicho, "uf": uf, "municipio": municipio, "porte": porte, "situacao": situacao, "cep": cep}
    run_id = db_module.make_run_id(params)
    db_module.ensure_run(conn, run_id, params, TARGET_LEADS)

    descobertos = await discovery.discover(icp, conn=conn, run_id=run_id, target_leads=TARGET_LEADS)

    # só os que ainda estão "descoberto" precisam passar pelo S3 nesta chamada —
    # leads já validados/descartados em execuções anteriores (retomada) são pulados
    for lead in descobertos:
        cnpj = lead["cnpj"]
        resultado = await validate_lead(cnpj, icp)
        db_module.upsert_lead(
            conn,
            run_id,
            cnpj,
            status=resultado.status,
            detalhe=resultado.detalhe.model_dump() if resultado.detalhe else None,
            discard_reason=resultado.discard_reason,
        )

    validados = db_module.list_leads(conn, run_id, status="validado")
    return conn, run_id, validados


@app.command()
def descobrir(
    nicho: str,
    uf: str | None = None,
    municipio: str | None = None,
    porte: str | None = None,
    situacao: str = "ativa",
    cep: str | None = None,
    db_path: str | None = None,
) -> None:
    """S0→S3: traduz o nicho em CNAE (`references/cnae.md`), descobre via busca
    avançada (teto fixo de 100 leads), valida cada lead via `route=cnpj`, e
    imprime o resultado em JSON — sempre JSON, decisão fechada da seção 11.

    `--cep` filtra por prefixo de CEP (ex. "0507") — é o jeito de restringir a
    um bairro/região dentro de um município, já que não há filtro de bairro
    nomeado na API (ver references/basecnpj.md).
    """
    icp = _resolve_icp_or_exit(nicho, uf, municipio, porte, situacao, cep)

    async def _pipeline() -> list[dict[str, Any]]:
        _conn, _run_id, validados = await _descobrir_ate_validar(
            icp, nicho=nicho, uf=uf, municipio=municipio, porte=porte, situacao=situacao, cep=cep, db_path=db_path
        )
        return [{"cnpj": v["cnpj"], "razao_social": (v["detalhe"] or {}).get("razao_social")} for v in validados]

    resultados = _run(_pipeline())
    typer.echo(json.dumps({"total": len(resultados), "leads": resultados}, indent=2, ensure_ascii=False, default=str))


@app.command()
def prospectar(
    nicho: str,
    uf: str | None = None,
    municipio: str | None = None,
    porte: str | None = None,
    situacao: str = "ativa",
    cep: str | None = None,
    db_path: str | None = None,
    sites_json: str | None = None,
) -> None:
    """S0→S4→S6 (sem S5 — decisão fechada, seção 11): descobre, valida,
    enriquece (quando há site candidato) e pontua. Sempre JSON, teto fixo de
    100 leads. `--cep` filtra por bairro/região (prefixo de CEP). `--sites-json`
    aponta pra um arquivo `{"cnpj": "url candidata"}` — achar a URL em si é
    responsabilidade do skill via busca web, não deste comando (regra de ouro
    da seção 6 do ARCTETURE.md).
    """
    icp = _resolve_icp_or_exit(nicho, uf, municipio, porte, situacao, cep)

    sites: dict[str, str] = {}
    if sites_json:
        sites = json.loads(Path(sites_json).read_text())

    async def _pipeline() -> dict[str, Any]:
        conn, run_id, validados = await _descobrir_ate_validar(
            icp, nicho=nicho, uf=uf, municipio=municipio, porte=porte, situacao=situacao, cep=cep, db_path=db_path
        )

        session = ScrapeSession()
        leads_json: list[dict[str, Any]] = []
        for v in validados:
            # reconstrói o ValidacaoResult completo (flags/cnae_match) a partir do
            # detalhe já persistido — sem nova chamada de rede (raw= evita o fetch)
            resultado = await validate_lead(v["cnpj"], icp, raw=v["detalhe"])
            if resultado.status != "validado":
                continue  # ICP mudou entre execuções — não deveria acontecer, mas não quebra

            enrichment = None
            candidate_url = sites.get(v["cnpj"])
            if candidate_url:
                razao_social = resultado.detalhe.razao_social if resultado.detalhe else None
                nome_fantasia = (
                    resultado.detalhe.estabelecimento_matriz.nome_fantasia
                    if resultado.detalhe and resultado.detalhe.estabelecimento_matriz
                    else None
                )
                email_cadastral = (
                    resultado.detalhe.estabelecimento_matriz.email
                    if resultado.detalhe and resultado.detalhe.estabelecimento_matriz
                    else None
                )
                enrichment = await enrich(
                    candidate_url,
                    session,
                    cnpj=v["cnpj"],
                    razao_social=razao_social,
                    nome_fantasia=nome_fantasia,
                    email_cadastral=email_cadastral,
                )

            score = compute_score(resultado, enrichment)
            leads_json.append(build_lead_json(resultado, score, enrichment))

        return export_leads(leads_json, max_leads=TARGET_LEADS)

    resultado_final = _run(_pipeline())
    typer.echo(json.dumps(resultado_final, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    app()
