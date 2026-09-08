from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from scripts.basecnpj import routes
from scripts.basecnpj.config import Settings

_DIGITS_RE = re.compile(r"\D")


def _only_digits(value: str) -> str:
    return _DIGITS_RE.sub("", value)


@dataclass
class Candidato:
    """Um candidato a lead sem CNPJ ainda — vem de fora do BaseCNPJ (lista do
    usuário, indicação). Diretórios comerciais automatizados ficam fora do v1
    (decisão fechada, seção 11 do ARCTETURE.md); esta função só resolve identidade
    para candidatos já fornecidos.
    """

    nome: str
    uf: str | None = None
    municipio: str | None = None


@dataclass
class ResolucaoResult:
    candidato: Candidato
    status: str  # "resolvido" | "nao_resolvido"
    cnpj: str | None = None
    fonte: str | None = None  # "sugestao" | "busca"
    match: dict[str, Any] | None = None


def _matches_geo(item: dict[str, Any], uf: str | None, municipio: str | None) -> bool:
    if uf is not None and item.get("uf") is not None and item["uf"] != uf:
        return False
    if (
        municipio is not None
        and item.get("municipio") is not None
        and item["municipio"].strip().lower() != municipio.strip().lower()
    ):
        return False
    return True


def _pick_unique_match(
    items: list[dict[str, Any]], uf: str | None, municipio: str | None
) -> dict[str, Any] | None:
    """Desempata por UF/município. Sem forma de desempatar e mais de um resultado,
    o match é ambíguo — nunca chuta, devolve None (quem chama marca nao_resolvido).
    """
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    if uf is None and municipio is None:
        return None
    filtrados = [item for item in items if _matches_geo(item, uf, municipio)]
    if len(filtrados) == 1:
        return filtrados[0]
    return None


async def resolve_candidato(
    candidato: Candidato,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> ResolucaoResult:
    """S2 — resolve um candidato sem CNPJ: `route=sugestao` primeiro (mais rápido),
    `route=busca` como busca textual mais ampla. Match ambíguo (ou nenhum resultado)
    vira `nao_resolvido`, sem nunca chutar entre candidatos.
    """
    sugestao = await routes.sugestao(candidato.nome, settings=settings, client=client)
    match = _pick_unique_match(sugestao.get("items", []), candidato.uf, candidato.municipio)
    fonte = "sugestao"

    if match is None:
        busca = await routes.busca(candidato.nome, settings=settings, client=client)
        match = _pick_unique_match(busca.get("items", []), candidato.uf, candidato.municipio)
        fonte = "busca"

    if match is None:
        return ResolucaoResult(candidato=candidato, status="nao_resolvido")

    cnpj_bruto = match.get("cnpj_formatado") or match.get("cnpj_completo") or ""
    cnpj = _only_digits(cnpj_bruto)
    if not cnpj:
        return ResolucaoResult(candidato=candidato, status="nao_resolvido")

    return ResolucaoResult(candidato=candidato, status="resolvido", cnpj=cnpj, fonte=fonte, match=match)
