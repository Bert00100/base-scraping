from __future__ import annotations

import time
from typing import Any

from scripts.pipeline.score import ScoreBreakdown
from scripts.pipeline.validate import ValidacaoResult
from scripts.scraping.enrich import EnrichmentResult

MAX_LEADS_POR_EXECUCAO = 100  # decisão fechada, seção 11 do ARCTETURE.md — sem override


def _proveniencia(fonte: str, rota_ou_url: str, timestamp: float) -> dict[str, Any]:
    return {"fonte": fonte, "rota_ou_url": rota_ou_url, "timestamp": timestamp}


def build_lead_json(
    validacao: ValidacaoResult,
    score: ScoreBreakdown,
    enrichment: EnrichmentResult | None = None,
    *,
    validado_em: float | None = None,
    enriquecido_em: float | None = None,
) -> dict[str, Any]:
    """Monta o JSON final de um lead (contrato em schemas/lead.md), com
    proveniência por campo (fonte, rota/URL, timestamp). Campo sem dado
    disponível simplesmente não aparece — o lead continua utilizável com menos
    campos, premissa central do ARCTETURE.md.
    """
    validado_em = validado_em if validado_em is not None else time.time()
    lead: dict[str, Any] = {"cnpj": validacao.cnpj}
    proveniencia: dict[str, Any] = {"cnpj": _proveniencia("basecnpj", "route=cnpj", validado_em)}

    detalhe = validacao.detalhe
    if detalhe is not None:
        campos_cadastrais: dict[str, Any] = {
            "razao_social": detalhe.razao_social,
            "capital_social": detalhe.capital_social,
            "porte": detalhe.porte_descricao,
            "natureza_juridica": detalhe.natureza_juridica_descricao,
            "cnae_principal": detalhe.cnae_principal(),
            "cnaes_secundarios": detalhe.cnaes_secundarios(),
        }

        matriz = detalhe.estabelecimento_matriz
        if matriz is not None:
            campos_cadastrais.update(
                {
                    "nome_fantasia": matriz.nome_fantasia,
                    "situacao_cadastral": matriz.situacao_descricao,
                    "data_abertura": matriz.data_inicio_atividade,
                    "email_cadastral": matriz.email,
                    "endereco": {
                        "logradouro": matriz.logradouro,
                        "municipio": matriz.municipio,
                        "uf": matriz.uf,
                        "cep": matriz.cep,
                    },
                }
            )

        if detalhe.telefones:
            primeiro = detalhe.telefones[0]
            campos_cadastrais["telefone_cadastral"] = (
                f"({primeiro.ddd}) {primeiro.numero}" if primeiro.ddd else primeiro.numero
            )

        matriz_filial_codigo = detalhe.matriz_filial_codigo()
        if matriz_filial_codigo is not None:
            campos_cadastrais["matriz_filial"] = "matriz" if matriz_filial_codigo == "1" else "filial"

        socios = getattr(detalhe, "socios", None)
        if socios:
            campos_cadastrais["socios"] = socios

        for campo, valor in campos_cadastrais.items():
            if valor in (None, [], {}):
                continue
            lead[campo] = valor
            proveniencia[campo] = _proveniencia("basecnpj", "route=cnpj", validado_em)

    lead["score"] = score.total
    lead["score_breakdown"] = score.as_dict()
    proveniencia["score"] = _proveniencia("pipeline", "S6", validado_em)

    if validacao.flags:
        lead["flags"] = validacao.flags

    if enrichment is not None and enrichment.site_matched:
        enriquecido_em = enriquecido_em if enriquecido_em is not None else time.time()
        origem = enrichment.site or "scraping"

        lead["site"] = enrichment.site
        proveniencia["site"] = _proveniencia("scraping", origem, enriquecido_em)

        if enrichment.emails:
            lead["emails"] = [
                {"valor": e.email, "nivel": e.nivel, "confianca": e.confianca} for e in enrichment.emails
            ]
            proveniencia["emails"] = _proveniencia("scraping", origem, enriquecido_em)

        if enrichment.telefones:
            lead["telefones"] = enrichment.telefones
            proveniencia["telefones"] = _proveniencia("scraping", origem, enriquecido_em)

        if enrichment.whatsapp:
            lead["whatsapp"] = enrichment.whatsapp
            proveniencia["whatsapp"] = _proveniencia("scraping", origem, enriquecido_em)

        if enrichment.redes_sociais:
            lead["redes_sociais"] = enrichment.redes_sociais
            proveniencia["redes_sociais"] = _proveniencia("scraping", origem, enriquecido_em)

    lead["proveniencia"] = proveniencia
    return lead


def export_leads(leads: list[dict[str, Any]], *, max_leads: int = MAX_LEADS_POR_EXECUCAO) -> dict[str, Any]:
    """Saída sempre em JSON (decisão fechada, seção 11). Teto fixo de
    `max_leads` — se mais leads chegarem aqui por algum motivo, mantém os de
    maior score em vez de truncar arbitrariamente.
    """
    ordenados = sorted(leads, key=lambda lead: lead.get("score", 0), reverse=True)
    limitados = ordenados[:max_leads]
    return {"total": len(limitados), "leads": limitados}
