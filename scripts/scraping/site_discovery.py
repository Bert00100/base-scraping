from __future__ import annotations

import re
from dataclasses import dataclass

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

