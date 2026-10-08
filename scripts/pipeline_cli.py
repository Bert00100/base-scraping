from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, NoReturn

import typer

from scripts.pipeline import db as db_module
from scripts.pipeline import discovery
from scripts.pipeline import icp as icp_module
from scripts.pipeline.resolve import Candidato, resolve_candidato
from scripts.pipeline.export import export_leads, build_lead_json
from scripts.pipeline.score import compute_score
from scripts.pipeline.validate import ValidacaoResult, validate_lead
from scripts.basecnpj.errors import AuthError, NotFoundError
from scripts.scraping.enrich import enrich
from scripts.scraping.http import ScrapeSession
from scripts.utils import only_digits

app = typer.Typer(help="Pipeline do base-scraping — S0→S3 (descobrir) e S0→S4→S6 (prospectar, sem S5).")

TARGET_LEADS = 100  # decisão fechada, seção 11 do ARCTETURE.md — sem override de CLI
MAX_ITENS_LISTA = 100  # teto de itens do `validar-lista`, mesmo valor do teto de leads
MOTIVO_404 = "cnpj nao encontrado no BaseCNPJ (404)"


class PreflightError(RuntimeError):
    """O `route=status` não respondeu `ok` — a descoberta não deve começar."""


def _exit_with_error(codigo: str, mensagem: str) -> NoReturn:
    typer.echo(json.dumps({"erro": codigo, "mensagem": mensagem}, ensure_ascii=False))
    raise typer.Exit(code=1)


def _run_or_exit(coro):
    try:
        return asyncio.run(coro)
    except AuthError:
        _exit_with_error(
            "token_invalido",
            "Token inválido, expirado ou sem permissão para a rota; conferir a variável BASECNPJ_TOKEN.",
        )
    except PreflightError as exc:
        _exit_with_error("preflight_falhou", str(exc))


def _resolve_icp_or_exit(
    nicho: str,
    uf: str | None,
    municipio: str | None,
    porte: str | None,
    situacao: str,
    cep: str | None,
    matriz: bool = False,
) -> icp_module.ICP:
    icp = icp_module.build_icp(
        nicho=nicho,
        uf=uf,
        municipio=municipio,
        porte=porte,
        situacao=situacao,
        cep=cep,
        matriz=matriz,
    )
    if icp.needs_confirmation:
        _exit_with_error(
            "nicho_nao_encontrado",
            (
                f"Nicho '{nicho}' não está em references/cnae.md. "
                "Confirme o(s) CNAE(s) certo(s) com o usuário antes de rodar a descoberta."
            ),
        )
    return icp


async def _exigir_preflight() -> None:
    status = await icp_module.preflight()
    if status.get("status") != "ok":
        raise PreflightError(f"preflight falhou: {status}")


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
    matriz: bool = False,
) -> tuple[Any, str, list[dict[str, Any]]]:
    """S0→S3: roda preflight, descoberta (com checkpoint) e validação dos leads
    ainda não processados. Devolve (conn, run_id, leads_validados_desta_execucao_em_diante).
    """
    await _exigir_preflight()

    conn = db_module.connect(Path(db_path) if db_path else None)
    params: dict[str, Any] = {
        "nicho": nicho,
        "uf": uf,
        "municipio": municipio,
        "porte": porte,
        "situacao": situacao,
        "cep": cep,
    }
    if matriz:
        params["matriz"] = True  # só quando usada, para não mudar o run_id de execuções antigas
    run_id = db_module.make_run_id(params)
    db_module.ensure_run(conn, run_id, params, TARGET_LEADS)

    descobertos = await discovery.discover(icp, conn=conn, run_id=run_id, target_leads=TARGET_LEADS)

    # só os que ainda estão "descoberto" precisam passar pelo S3 nesta chamada —
    # leads já validados/descartados em execuções anteriores (retomada) são pulados
    for lead in descobertos:
        cnpj = lead["cnpj"]
        try:
            resultado = await validate_lead(cnpj, icp)
        except NotFoundError:
            db_module.upsert_lead(
                conn,
                run_id,
                cnpj,
                status="nao_resolvido",
                discard_reason=MOTIVO_404,
            )
            continue
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


def _listar_descartados(conn: Any, run_id: str) -> list[dict[str, Any]]:
    """Leads que não chegaram à saída (descartados na validação ou não resolvidos)."""
    descartados: list[dict[str, Any]] = []
    for status in ("descartado", "nao_resolvido"):
        for lead in db_module.list_leads(conn, run_id, status=status):
            descartados.append({"cnpj": lead["cnpj"], "motivo": lead["discard_reason"]})
    return descartados


async def _enriquecer_e_pontuar(
    resultados: list[ValidacaoResult],
    sites: dict[str, str],
) -> list[dict[str, Any]]:
    """S4+S6: para cada resultado validado, enriquece (quando há site candidato em
    `sites`) e pontua. Devolve os JSONs de lead, ainda sem ordenar/limitar.
    """
    session = ScrapeSession()
    leads_json: list[dict[str, Any]] = []
    for resultado in resultados:
        enrichment = None
        candidate_url = sites.get(resultado.cnpj)
        if candidate_url:
            detalhe = resultado.detalhe
            estab = detalhe.estabelecimento_matriz if detalhe else None
            enrichment = await enrich(
                candidate_url,
                session,
                cnpj=resultado.cnpj,
                razao_social=detalhe.razao_social if detalhe else None,
                nome_fantasia=estab.nome_fantasia if estab else None,
                telefone_cadastral=detalhe.telefone_principal() if detalhe else None,
                email_cadastral=estab.email if estab else None,
            )

        score = compute_score(resultado, enrichment)
        leads_json.append(build_lead_json(resultado, score, enrichment))
    return leads_json


@app.command()
def descobrir(
    nicho: str,
    uf: str | None = None,
    municipio: str | None = None,
    porte: str | None = None,
    situacao: str = "ativa",
    cep: str | None = None,
    matriz: bool = False,
    db_path: str | None = None,
) -> None:
    """S0→S3: traduz o nicho em CNAE (`references/cnae.md`), descobre via busca
    avançada (teto fixo de 100 leads), valida cada lead via `route=cnpj`, e
    imprime o resultado em JSON — sempre JSON, decisão fechada da seção 11.

    `--cep` filtra por prefixo de CEP (ex. "0507") — é o jeito de restringir a
    um bairro/região dentro de um município, já que não há filtro de bairro
    nomeado na API (ver references/basecnpj.md). `--matriz` restringe a
    descoberta a estabelecimentos matriz (exclui filiais).
    """
    icp = _resolve_icp_or_exit(nicho, uf, municipio, porte, situacao, cep, matriz)

    async def _pipeline() -> dict[str, Any]:
        conn, run_id, validados = await _descobrir_ate_validar(
            icp,
            nicho=nicho,
            uf=uf,
            municipio=municipio,
            porte=porte,
            situacao=situacao,
            cep=cep,
            db_path=db_path,
            matriz=matriz,
        )
        leads = [{"cnpj": v["cnpj"], "razao_social": (v["detalhe"] or {}).get("razao_social")} for v in validados]
        return {"total": len(leads), "leads": leads, "descartados": _listar_descartados(conn, run_id)}

    resultado_final = _run_or_exit(_pipeline())
    typer.echo(json.dumps(resultado_final, indent=2, ensure_ascii=False, default=str))


@app.command()
def prospectar(
    nicho: str,
    uf: str | None = None,
    municipio: str | None = None,
    porte: str | None = None,
    situacao: str = "ativa",
    cep: str | None = None,
    matriz: bool = False,
    db_path: str | None = None,
    sites_json: str | None = None,
) -> None:
    """S0→S4→S6 (sem S5 — decisão fechada, seção 11): descobre, valida,
    enriquece (quando há site candidato) e pontua. Sempre JSON, teto fixo de
    100 leads. `--cep` filtra por bairro/região (prefixo de CEP). `--matriz`
    descobre só matrizes. `--sites-json`
    aponta pra um arquivo `{"cnpj": "url candidata"}` — achar a URL em si é
    responsabilidade do skill via busca web, não deste comando (regra de ouro
    da seção 6 do ARCTETURE.md).
    """
    icp = _resolve_icp_or_exit(nicho, uf, municipio, porte, situacao, cep, matriz)

    sites: dict[str, str] = {}
    if sites_json:
        sites = json.loads(Path(sites_json).read_text())

    async def _pipeline() -> dict[str, Any]:
        conn, run_id, validados = await _descobrir_ate_validar(
            icp,
            nicho=nicho,
            uf=uf,
            municipio=municipio,
            porte=porte,
            situacao=situacao,
            cep=cep,
            db_path=db_path,
            matriz=matriz,
        )

        resultados: list[ValidacaoResult] = []
        for v in validados:
            # reconstrói o ValidacaoResult completo (flags/cnae_match) a partir do
            # detalhe já persistido — sem nova chamada de rede (raw= evita o fetch)
            resultado = await validate_lead(v["cnpj"], icp, raw=v["detalhe"])
            if resultado.status != "validado":
                continue  # ICP mudou entre execuções — não deveria acontecer, mas não quebra
            resultados.append(resultado)

        leads_json = await _enriquecer_e_pontuar(resultados, sites)
        saida = export_leads(leads_json, max_leads=TARGET_LEADS)
        saida["descartados"] = _listar_descartados(conn, run_id)
        return saida

    resultado_final = _run_or_exit(_pipeline())
    typer.echo(json.dumps(resultado_final, indent=2, ensure_ascii=False, default=str))


def _ler_lista_ou_exit(arquivo: str) -> list[dict[str, Any]]:
    try:
        itens = json.loads(Path(arquivo).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _exit_with_error("entrada_invalida", f"não foi possível ler '{arquivo}' como JSON: {exc}")
    if not isinstance(itens, list) or not all(
        isinstance(item, dict) and (item.get("cnpj") or item.get("nome")) for item in itens
    ):
        _exit_with_error(
            "entrada_invalida",
            'O arquivo deve ser uma lista de {"cnpj": ...} ou {"nome": ..., "uf"?, "municipio"?}.',
        )
    return itens


@app.command("validar-lista")
def validar_lista(
    arquivo: str = typer.Option(..., help="JSON com a lista de CNPJs/nomes"),
    situacao: str = "ativa",
    sites_json: str | None = None,
) -> None:
    """S2→S3→S4→S6 para uma lista própria (sem descoberta): `--arquivo` é um JSON
    com itens `{"cnpj": ...}` ou `{"nome": ..., "uf"?, "municipio"?}`, no máximo
    100 itens (o excedente é ignorado e informado na saída). Nome é resolvido via
    `route=sugestao`/`route=busca`; ambíguo ou sem resultado vai para
    `nao_resolvidos`. A validação não checa CNAE (a lista não tem nicho).
    `--sites-json` funciona como em `prospectar`.
    """
    itens = _ler_lista_ou_exit(arquivo)
    ignorados = max(0, len(itens) - MAX_ITENS_LISTA)
    itens = itens[:MAX_ITENS_LISTA]

    sites: dict[str, str] = {}
    if sites_json:
        sites = json.loads(Path(sites_json).read_text())

    codigo_situacao = icp_module.SITUACAO_CODIGOS.get(situacao.strip().lower(), situacao)
    icp = icp_module.ICP(nicho="lista", cnaes=[], situacao=codigo_situacao)

    async def _pipeline() -> dict[str, Any]:
        await _exigir_preflight()

        descartados: list[dict[str, Any]] = []
        nao_resolvidos: list[dict[str, Any]] = []
        validados: list[ValidacaoResult] = []
        vistos: set[str] = set()

        for item in itens:
            if item.get("cnpj"):
                cnpj = only_digits(str(item["cnpj"]))
                if len(cnpj) != 14:
                    nao_resolvidos.append({"cnpj": item["cnpj"], "motivo": "cnpj inválido (não tem 14 dígitos)"})
                    continue
            else:
                resolucao = await resolve_candidato(
                    Candidato(nome=item["nome"], uf=item.get("uf"), municipio=item.get("municipio"))
                )
                if resolucao.status != "resolvido" or resolucao.cnpj is None:
                    nao_resolvidos.append({"nome": item["nome"], "motivo": "sem match único na sugestão/busca"})
                    continue
                cnpj = resolucao.cnpj

            if cnpj in vistos:
                continue
            vistos.add(cnpj)

            try:
                resultado = await validate_lead(cnpj, icp)
            except NotFoundError:
                descartados.append({"cnpj": cnpj, "motivo": MOTIVO_404})
                continue
            if resultado.status == "validado":
                validados.append(resultado)
            else:
                descartados.append({"cnpj": cnpj, "motivo": resultado.discard_reason})

        leads_json = await _enriquecer_e_pontuar(validados, sites)
        saida = export_leads(leads_json, max_leads=TARGET_LEADS)
        saida["descartados"] = descartados
        saida["nao_resolvidos"] = nao_resolvidos
        if ignorados:
            saida["aviso"] = f"{ignorados} item(ns) além do teto de {MAX_ITENS_LISTA} foram ignorados"
        return saida

    resultado_final = _run_or_exit(_pipeline())
    typer.echo(json.dumps(resultado_final, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    app()
