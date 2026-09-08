from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.scraping.http import ScrapeSession, fetch

_NON_DIGIT_RE = re.compile(r"\D")


def _only_digits(value: str) -> str:
    return _NON_DIGIT_RE.sub("", value)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


@dataclass
class MatchResult:
    matched: bool
    sinais: list[str]  # quais sinais bateram: "cnpj", "razao_social", "nome_fantasia", "telefone"


def validar_match(
    html: str,
    *,
    cnpj: str,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    telefone: str | None = None,
) -> MatchResult:
    """4.1 do ARCTETURE.md — o site precisa mencionar o CNPJ, a razão social, o
    nome fantasia ou o telefone. Sem nenhum desses sinais, é match fraco: não
    confirma o site (quem chama descarta em vez de gravar lixo).
    """
    texto = _normalize_text(html)
    texto_digitos = _only_digits(html)
    sinais: list[str] = []

    cnpj_digitos = _only_digits(cnpj)
    if cnpj_digitos and cnpj_digitos in texto_digitos:
        sinais.append("cnpj")

    if razao_social and _normalize_text(razao_social) in texto:
        sinais.append("razao_social")

    if nome_fantasia and _normalize_text(nome_fantasia) in texto:
        sinais.append("nome_fantasia")

    if telefone:
        telefone_digitos = _only_digits(telefone)
        if telefone_digitos and telefone_digitos in texto_digitos:
            sinais.append("telefone")

    return MatchResult(matched=bool(sinais), sinais=sinais)


@dataclass
class SiteResult:
    url: str
    matched: bool
    sinais: list[str]
    status_code: int | None = None
    erro: str | None = None


async def discover_and_validate_site(
    candidate_url: str,
    session: ScrapeSession,
    *,
    cnpj: str,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    telefone: str | None = None,
    **fetch_kwargs,
) -> SiteResult:
    """Busca a URL candidata e valida se ela é mesmo o site da empresa.

    A descoberta da URL candidata em si (busca na web) é responsabilidade do
    skill/Claude Code, não deste script — "regra de ouro" da seção 6 do
    ARCTETURE.md: os scripts entregam dado, quem interpreta/pesquisa é o Claude
    executando o skill. Esta função só busca+valida uma URL já sugerida.
    """
    try:
        pagina = await fetch(candidate_url, session, **fetch_kwargs)
    except Exception as exc:  # PageBudgetExceeded, RobotsDisallowed, erros de rede
        return SiteResult(url=candidate_url, matched=False, sinais=[], erro=f"{type(exc).__name__}: {exc}")

    match = validar_match(
        pagina["text"],
        cnpj=cnpj,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        telefone=telefone,
    )
    return SiteResult(
        url=pagina["url"], matched=match.matched, sinais=match.sinais, status_code=pagina["status_code"]
    )
